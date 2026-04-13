import pytest
from api.identity.tokens import generate_token, hash_token, verify_token, TOKEN_PREFIX


def test_generate_token_has_prefix_and_sufficient_entropy():
    t = generate_token()
    assert t.startswith(TOKEN_PREFIX)
    assert len(t) >= 40
    assert generate_token() != generate_token()


def test_hash_token_produces_salted_output():
    h = hash_token("amu_test_token")
    assert "$" in h
    salt, digest = h.split("$", 1)
    assert len(salt) == 32
    assert len(digest) == 64


def test_verify_token_correct_returns_true():
    token = generate_token()
    stored = hash_token(token)
    assert verify_token(token, stored) is True


def test_verify_token_wrong_returns_false():
    token = generate_token()
    stored = hash_token(token)
    assert verify_token(token + "x", stored) is False
    assert verify_token("completely_different", stored) is False


def test_verify_token_malformed_stored_returns_false():
    assert verify_token("whatever", "no_dollar_sign") is False
    assert verify_token("whatever", "") is False
