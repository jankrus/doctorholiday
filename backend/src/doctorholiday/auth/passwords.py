"""Password policy and hashing with Argon2id (BR-01), via argon2-cffi. No custom crypto.

The parameters are argon2-cffi's defaults, the RFC 9106 low-memory profile (t=3, m=64 MiB, p=4).
They are encoded in every hash, so raising them later keeps old hashes verifiable.
"""

import functools
import gzip
import logging
import secrets
from importlib import resources

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


# Words a password must not contain because they are the first thing an attacker tries against
# this service (NIST SP 800-63B, 3.1.1.2: context-specific words). Compared without spaces,
# hyphens and dots, casefolded.
_SERVICE_WORDS = ("doctorholiday",)


@functools.cache
def _common_passwords() -> frozenset[str]:
    """The blocklist, built by scripts/build-common-passwords.py: entries of 12-128 characters
    from the NCSC top 100,000 and the xato.net top 1,000,000, casefolded."""
    data = resources.files(__package__).joinpath("common_passwords.txt.gz").read_bytes()
    return frozenset(gzip.decompress(data).decode("utf-8").splitlines())


def _squash(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch not in " -_.")


def is_common_password(password: str, *, email: str) -> bool:
    """True if the password is on the blocklist of breached passwords, contains the account's
    e-mail address or the service name (BR-01). Case does not matter."""
    folded = password.casefold()
    if folded in _common_passwords() or email.casefold() in folded:
        return True
    squashed = _squash(password)
    return any(word in squashed for word in _SERVICE_WORDS)
