from __future__ import annotations

import pytest

from utils.collection_share import (
    CollectionShareError,
    create_collection_share_token,
    verify_collection_share_token,
)


SECRET = "test-secret-that-is-not-production"


def test_collection_share_roundtrip() -> None:
    token = create_collection_share_token(12345, now=1_000, ttl_seconds=600, secret=SECRET)
    assert verify_collection_share_token(token, now=1_100, secret=SECRET) == 12345


def test_collection_share_rejects_tampering() -> None:
    token = create_collection_share_token(12345, now=1_000, ttl_seconds=600, secret=SECRET)
    uid, expires, signature = token.split(".")
    forged = f"99999.{expires}.{signature}"
    with pytest.raises(CollectionShareError, match="invalid_signature"):
        verify_collection_share_token(forged, now=1_100, secret=SECRET)


def test_collection_share_rejects_expired_token() -> None:
    token = create_collection_share_token(12345, now=1_000, ttl_seconds=300, secret=SECRET)
    with pytest.raises(CollectionShareError, match="expired"):
        verify_collection_share_token(token, now=1_301, secret=SECRET)


def test_collection_share_has_minimum_and_maximum_ttl() -> None:
    short = create_collection_share_token(1, now=1_000, ttl_seconds=1, secret=SECRET)
    long = create_collection_share_token(1, now=1_000, ttl_seconds=999_999_999, secret=SECRET)
    assert int(short.split(".")[1]) == 1_300
    assert int(long.split(".")[1]) == 1_000 + 30 * 24 * 3600
