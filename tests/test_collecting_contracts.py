"""Request contracts, safe image preparation, and one-MiniApp architecture."""

from pathlib import Path
from uuid import uuid4
from io import BytesIO
import importlib.util
import pytest
from pydantic import ValidationError
from PIL import Image
from source_features import schemas

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "1", [], {}, 2**54])
def test_ids_reject_ambiguous_values(value):
    with pytest.raises(ValidationError):
        schemas.Item(character_id=value, quantity=1)


@pytest.mark.parametrize("value", [True, 0, -1, 21, 1.2, "3", [], None])
def test_quantity_is_strict_and_bounded(value):
    with pytest.raises(ValidationError):
        schemas.Item(character_id=1, quantity=value)


@pytest.mark.parametrize("field", ["user_id", "uid", "seller_id", "coins", "is_admin"])
def test_browser_cannot_supply_identity_or_balance(field):
    with pytest.raises(ValidationError):
        schemas.Listing(
            character_id=1, quantity=1, price=2, request_id=uuid4(), **{field: 123}
        )


@pytest.mark.parametrize(
    "action", ["credit", "withdraw", "settle", "delete", "<script>"]
)
def test_only_explicit_market_actions(action):
    with pytest.raises(ValidationError):
        schemas.MarketAction(action=action, version=1, request_id=uuid4())


@pytest.mark.parametrize("enabled", ["yes", 1, 0, [], None])
def test_preferences_are_not_truthy_strings(enabled):
    with pytest.raises(ValidationError):
        schemas.Toggle(enabled=enabled)


def test_event_manifest_is_data_only_and_dates_require_timezone():
    base = dict(
        title="Evento de teste",
        description="Somente dados de teste",
        character_ids=[1],
        goal=3,
        reward_label="Participante",
        starts_at="2026-09-25T10:00:00Z",
        ends_at="2026-09-26T10:00:00Z",
        request_id=str(uuid4()),
    )
    assert schemas.EventSpec(**base)
    for extras in [
        {"script": "eval(x)"},
        {"reward_coins": 1000},
        {"image_url": "http://localhost"},
        {"starts_at": "2026-09-25T10:00:00"},
    ]:
        with pytest.raises(ValidationError):
            schemas.EventSpec(**{**base, **extras})


def test_schema_generated_contract_matches_server():
    spec = importlib.util.spec_from_file_location(
        "collecting_codegen", ROOT / "scripts/generate_collecting_types.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (
        ROOT / "aninexus_frontend/src/features/collecting/contracts.generated.ts"
    ).read_text() == module.build()


def test_image_is_reencoded_without_metadata():
    from source_features.discovery import prepare_image

    buf = BytesIO()
    Image.new("RGB", (20, 30)).save(buf, format="PNG")
    result = prepare_image(buf.getvalue())
    with Image.open(BytesIO(result)) as img:
        assert img.format == "JPEG" and img.size == (20, 30) and not img.getexif()


@pytest.mark.parametrize(
    "data",
    [b"", b"<svg></svg>", b"<html>not image</html>", b"\x00" * 2200000],
    ids=["empty", "svg", "html", "oversized"],
)
def test_image_input_validation(data):
    from source_features.discovery import prepare_image
    from source_features.errors import FeatureError

    with pytest.raises(FeatureError):
        prepare_image(data)


def test_new_screens_use_only_shared_auth_and_shell():
    router = (ROOT / "source_features/router.py").read_text()
    assert "API_PREFIX" in router and "_require_user" in router
    assert "Depends(actor)" in router and "Depends(administrator)" in router
    for file in (ROOT / "aninexus_frontend/src/features/collecting").glob("*.tsx"):
        text = file.read_text()
        assert (
            "<iframe" not in text
            and "window.open(" not in text
            and "createRoot" not in text
        )
    assert "miniapp_url(tab, **params)" in (ROOT / "commands/collecting.py").read_text()


def test_schema_does_not_rewrite_existing_economy():
    sql = (ROOT / "migrations/001_collecting.sql").read_text()
    assert "UPDATE users SET coins" not in sql
    assert "source_guard_collection" in sql
    assert "ON DELETE CASCADE" in sql
