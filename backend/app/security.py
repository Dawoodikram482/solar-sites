"""Password hashing and session tokens, using only the Python standard library.

Passwords: scrypt (hashlib.scrypt). It is a deliberately slow, memory-hard
hash, so stolen hashes are expensive to brute-force. Every password gets its
own random salt, so two users with the same password get different hashes.

Session tokens: 32 random bytes from `secrets` (a cryptographically secure
generator). The browser gets the raw token in a cookie; the database only
stores its SHA-256 hash. If the database leaks, the attacker still cannot
log in as anyone, because they cannot turn a hash back into the cookie value.
"""

import hashlib
import hmac
import secrets

# scrypt cost parameters. n=2**14, r=8, p=1 is the commonly recommended
# interactive-login setting (~16 MB memory, well under 100 ms per hash).
_N, _R, _P = 2**14, 8, 1
_KEY_LEN = 32


def hash_password(password: str) -> str:
    """Return 'scrypt$<salt hex>$<hash hex>' — salt and hash stored together."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY_LEN)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Hash the attempt with the stored salt and compare in constant time."""
    try:
        _scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    attempt = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt_hex), n=_N, r=_R, p=_P, dklen=_KEY_LEN
    )
    # compare_digest takes the same time whether the first or last byte differs,
    # so response timing does not leak how close a guess was.
    return hmac.compare_digest(attempt.hex(), digest_hex)


# A hash of a random password, used when a login names an unknown email.
# We still run verify_password against it so that "unknown email" and
# "wrong password" take the same time (see auth.login).
DUMMY_HASH = hash_password(secrets.token_hex(16))


def new_token() -> str:
    """A random, URL-safe token (used for both session and CSRF tokens)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 is fine here (unlike for passwords): the token is already
    256 bits of randomness, so there is nothing to brute-force."""
    return hashlib.sha256(token.encode()).hexdigest()
