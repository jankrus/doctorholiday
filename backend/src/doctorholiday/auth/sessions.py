"""Session tokens and the session cookie (ADR-001: server-side sessions, BR-05).

The token is 256 random bits and lives only in the client's cookie. The database stores its
SHA-256, so a leaked `sessions` table does not contain usable session IDs. A plain hash is
enough: the token has full entropy, unlike a password, and needs no salt or slow hash.
"""

import hashlib
import re
import secrets

from fastapi import Request, Response

COOKIE_NAME = "__Host-dh_session"
_TOKEN_BYTES = 32
# token_urlsafe(32): 43 characters of the base64url alphabet, no padding.
_TOKEN_FORMAT = re.compile(r"[A-Za-z0-9_-]{43}")
# __Host- prefix: the browser only accepts the cookie with Secure, Path=/ and without Domain.
# No Max-Age or Expires: the cookie ends with the browser session, the server enforces the
# timeouts. Written by hand to match SetSessionCookie / ClearSessionCookie in openapi.yaml.
_ATTRIBUTES = "HttpOnly; Secure; SameSite=Strict; Path=/"


def new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def token_from_cookie(request: Request) -> str | None:
    """The session token from the request, or None if absent or not shaped like a token."""
    value = request.cookies.get(COOKIE_NAME)
    if value is None or not _TOKEN_FORMAT.fullmatch(value):
        return None
    return value


def set_session_cookie(response: Response, token: str) -> None:
    response.headers.append("Set-Cookie", f"{COOKIE_NAME}={token}; {_ATTRIBUTES}")


def clear_session_cookie(response: Response) -> None:
    response.headers.append("Set-Cookie", f"{COOKIE_NAME}=; Max-Age=0; {_ATTRIBUTES}")
