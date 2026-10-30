"""Password hashing with Argon2id (BR-01), via argon2-cffi. No custom crypto.

The parameters are argon2-cffi's defaults, the RFC 9106 low-memory profile (t=3, m=64 MiB, p=4).
They are encoded in every hash, so raising them later keeps old hashes verifiable.
"""

import functools
import logging
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

logger = logging.getLogger(__name__)

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        # Any other failure means the stored hash cannot be decoded. Never log the hash itself.
        logger.warning("stored password hash is not a valid Argon2 hash")
        return False


@functools.cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(16))


def verify_dummy(password: str) -> None:
    """Spend the same time as `verify_password` when there is no account to check against.

    Without it a login for an unknown e-mail answers measurably faster and reveals that the
    account does not exist (BR-03).
    """
    verify_password(_dummy_hash(), password)
