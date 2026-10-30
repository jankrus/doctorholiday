"""Rate limiting and temporary lockout (BR-03, #14).

A `Limit` allows `max_attempts` counted attempts per key within `window`; the attempt that
reaches it locks the key for `lockout`, and until then every request with that key answers `429`
before doing the protected work. After a lockout, attempts still inside the window lock again at
once. What counts as an attempt is the endpoint's choice:

| Endpoint | Scope | Counts | Default |
| --- | --- | --- | --- |
| Login | `LOGIN_IP`, `LOGIN_ACCOUNT` | failures | 20 per IP, 5 per e-mail / 15 min, 15 min lock |
| Registration | `REGISTRATION_IP` | every request | 10 per IP / 60 min, 60 min lock |

The other scopes of BR-03 (MFA verification, invitation acceptance, password reset,
re-authentication) exist in the schema; their endpoints add a `Limit` here when they are built.

Login counts failures twice: per client IP (guessing against many accounts) and per e-mail
(guessing one account from many IPs). A successful login resets the e-mail counter, never the IP
one, so one known account cannot reset the IP limit between guesses. The e-mail counter exists
whether or not an account has the address, so a lockout reveals no accounts; the price is that
anyone can lock an account for the lockout time, which is why the values are configurable.

Counters are stored in the database, not in process memory, so they hold across restarts and
pods, and they are compared with the database clock (repositories/rate_limits.py).
"""

import hashlib
import math
from dataclasses import dataclass
from datetime import timedelta
from ipaddress import IPv6Address, ip_network

from pydantic import EmailStr
from sqlalchemy.orm import Session

from doctorholiday.config import Settings
from doctorholiday.models import IPAddress, RateLimit, RateLimitScope
from doctorholiday.repositories import rate_limits

# A single IPv6 client usually has a whole /64, so its addresses share one counter.
_IPV6_PREFIX = 64


@dataclass(frozen=True)
class Limit:
    scope: RateLimitScope
    max_attempts: int
    window: timedelta
    lockout: timedelta


def login_limits(settings: Settings) -> tuple[Limit, Limit]:
    """Per client IP and per e-mail address."""
    window = timedelta(minutes=settings.login_failure_window_minutes)
    lockout = timedelta(minutes=settings.login_lockout_minutes)
    return (
        Limit(RateLimitScope.LOGIN_IP, settings.login_max_failures_per_ip, window, lockout),
        Limit(
            RateLimitScope.LOGIN_ACCOUNT, settings.login_max_failures_per_account, window, lockout
        ),
    )


def registration_limit(settings: Settings) -> Limit:
    """Per client IP; the lock lasts as long as the window."""
    window = timedelta(minutes=settings.registration_window_minutes)
    return Limit(RateLimitScope.REGISTRATION_IP, settings.registration_max_per_ip, window, window)


def ip_key(ip: IPAddress | None) -> str:
    if ip is None:
        return "unknown"
    if isinstance(ip, IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ip_network(f"{ip}/{_IPV6_PREFIX}", strict=False))
    return str(ip)


def account_key(email: EmailStr) -> str:
    # Case-insensitive like users.email (citext), so case variants share one counter.
    return email.lower()


def _key_hash(key: str) -> bytes:
    return hashlib.sha256(key.encode()).digest()


class RateLimiter:
    """The counters of one request, locked until the request transaction ends.

    Create it before the protected work and answer `429` if `retry_after()` is not None; then
    `count()` the request if it counts, or `reset()` a scope (e.g. after a successful login).
    """

    def __init__(self, db: Session, *checks: tuple[Limit, str]) -> None:
        self._db = db
        for limit in {limit.scope: limit for limit, _ in checks}.values():
            rate_limits.delete_stale_counters(db, scope=limit.scope, window=limit.window)
        self._now = rate_limits.database_now(db)
        # Locked in one global order, so two requests never wait for each other's rows in
        # opposite order (no deadlock).
        keyed = sorted(
            ((limit, _key_hash(key)) for limit, key in checks),
            key=lambda check: (check[0].scope.value, check[1]),
        )
        self._counters: list[tuple[Limit, RateLimit]] = [
            (limit, rate_limits.lock_counter(db, scope=limit.scope, key_hash=key_hash))
            for limit, key_hash in keyed
        ]

    def retry_after(self) -> int | None:
        """Seconds until every lockout of this request is over, or None if none is active."""
        remaining = [
            counter.locked_until - self._now
            for _, counter in self._counters
            if counter.locked_until is not None and counter.locked_until > self._now
        ]
        if not remaining:
            return None
        return max(1, math.ceil(max(remaining).total_seconds()))

    def count(self) -> list[RateLimitScope]:
        """Count one attempt against every limit; returns the scopes whose lockout starts now."""
        locked = []
        for limit, counter in self._counters:
            if counter.window_started_at <= self._now - limit.window:
                counter.window_started_at = self._now
                counter.attempts = 0
            counter.attempts += 1
            if counter.attempts >= limit.max_attempts:
                counter.locked_until = self._now + limit.lockout
                locked.append(limit.scope)
        self._db.flush()
        return locked

    def reset(self, scope: RateLimitScope) -> None:
        for limit, counter in self._counters:
            if limit.scope is scope:
                rate_limits.delete_counter(self._db, counter)
