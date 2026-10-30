"""Login rate limiting and temporary lockout (#14, BR-03).

Every login counts failures twice: per client IP (online guessing against many accounts) and per
e-mail address (guessing one account from many IPs). A counter that reaches its limit within the
window locks its key for the lockout time; until then every login with that key answers `429`
without checking the password. A successful login resets the e-mail counter, never the IP one,
so one known account cannot be used to reset the IP limit between guesses.

The e-mail counter exists whether or not an account has the address, so a lockout looks the same
for every e-mail and reveals no accounts (BR-03). The price is that anyone can lock an account
for the lockout time with failed logins; the limits and times are configurable for that reason.

Counters are stored in the database, not in process memory, so they hold across restarts and
pods, and they are compared with the database clock (repositories/login_throttles.py).
"""

import hashlib
import math
from datetime import timedelta
from ipaddress import IPv6Address, ip_network

from pydantic import EmailStr
from sqlalchemy.orm import Session

from doctorholiday.config import Settings
from doctorholiday.models import IPAddress, ThrottleScope
from doctorholiday.repositories import login_throttles

# A single IPv6 client usually has a whole /64, so its addresses share one counter.
_IPV6_PREFIX = 64


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


class LoginThrottle:
    """The counters of one login attempt, locked until the request transaction ends.

    Create it before the password check and call `retry_after()`, then exactly one of
    `record_failure()` or `record_success()`.
    """

    def __init__(
        self, db: Session, settings: Settings, *, ip: IPAddress | None, email: EmailStr
    ) -> None:
        self._db = db
        self._window = timedelta(minutes=settings.login_failure_window_minutes)
        self._lockout = timedelta(minutes=settings.login_lockout_minutes)
        login_throttles.delete_stale_counters(db, window=self._window)
        self._now = login_throttles.database_now(db)
        # Always IP first, then account, so two logins never wait for each other's rows in
        # opposite order (no deadlock).
        ip_counter = login_throttles.lock_counter(
            db, scope=ThrottleScope.IP, key_hash=_key_hash(ip_key(ip))
        )
        self._account = login_throttles.lock_counter(
            db, scope=ThrottleScope.ACCOUNT, key_hash=_key_hash(account_key(email))
        )
        self._counters = [
            (ip_counter, settings.login_max_failures_per_ip),
            (self._account, settings.login_max_failures_per_account),
        ]

    def retry_after(self) -> int | None:
        """Seconds until every lockout of this attempt is over, or None if none is active."""
        remaining = [
            counter.locked_until - self._now
            for counter, _ in self._counters
            if counter.locked_until is not None and counter.locked_until > self._now
        ]
        if not remaining:
            return None
        return max(1, math.ceil(max(remaining).total_seconds()))

    def record_failure(self) -> list[ThrottleScope]:
        """Count a failed login; returns the scopes whose lockout starts with it."""
        locked = []
        for counter, limit in self._counters:
            if counter.window_started_at <= self._now - self._window:
                counter.window_started_at = self._now
                counter.failures = 0
            counter.failures += 1
            if counter.failures >= limit:
                counter.locked_until = self._now + self._lockout
                locked.append(counter.scope)
        self._db.flush()
        return locked

    def record_success(self) -> None:
        login_throttles.delete_counter(self._db, self._account)
