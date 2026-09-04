from __future__ import annotations

from utils.catalog_records import unwrap_records


def test_unwrap_records_accepts_supported_container_shapes() -> None:
    direct = [{"id": 1}, "ignore", {"id": 2}]
    assert unwrap_records(direct) == [{"id": 1}, {"id": 2}]

    for key in ("records", "items", "data", "animes", "catalogo", "results"):
        payload = {key: [{"id": 3}, None, {"id": 4}]}
        assert unwrap_records(payload) == [{"id": 3}, {"id": 4}]


def test_unwrap_records_keeps_original_first_list_fallback() -> None:
    assert unwrap_records({
        "metadata": {"version": 1},
        "unknown": [{"id": 9}],
        "other": [{"id": 10}],
    }) == [{"id": 9}]
    assert unwrap_records({"metadata": {"version": 1}}) == []
    assert unwrap_records("invalid") == []
