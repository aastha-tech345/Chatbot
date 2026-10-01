import bcrypt
import pytest

from app.crypto import hash_password, verify_password


def test_password_roundtrip_and_wrong_password():
    hashed = hash_password('synthetic-password')
    assert hashed.startswith('$2b$12$')
    assert verify_password('synthetic-password', hashed)
    assert not verify_password('wrong-password', hashed)


@pytest.mark.parametrize('prefix', [b'2a', b'2b'])
def test_existing_bcrypt_hashes(prefix):
    hashed = bcrypt.hashpw(b'existing-password', bcrypt.gensalt(rounds=4, prefix=prefix)).decode()
    assert verify_password('existing-password', hashed)


def test_legacy_utf8_truncation_is_preserved():
    password = '界' * 30
    hashed = bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=4)).decode()
    assert verify_password(password, hashed)
    assert verify_password(password, hash_password(password))


@pytest.mark.parametrize('hashed', ['', 'not-a-hash', 'invalid-界'])
def test_malformed_hash_fails_closed(hashed):
    assert not verify_password('password', hashed)


def test_null_password_fails_closed():
    assert not verify_password('password\0', hash_password('password'))
