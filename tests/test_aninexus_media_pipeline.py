from io import BytesIO
from pathlib import Path

from PIL import Image

from utils.portrait_image import crop_portrait_bytes


ROOT = Path(__file__).resolve().parents[1]


def test_portrait_processor_outputs_exact_two_by_three_ratio():
    source = Image.new("RGB", (800, 1200), "white")
    raw = BytesIO()
    source.save(raw, format="JPEG")

    output, metadata = crop_portrait_bytes(raw.getvalue())
    with Image.open(BytesIO(output)) as processed:
        width, height = processed.size

    assert width * 3 == height * 2
    assert metadata["output_width"] == width
    assert metadata["output_height"] == height
    assert metadata["output_ratio"] == round(2 / 3, 6)


def test_media_admin_requires_admin_and_rights_confirmation():
    source = (ROOT / "webapp_routes" / "aninexus_admin_media.py").read_text(encoding="utf-8")

    assert "is_admin(user_id)" in source
    assert '"rights_confirmed"' in source
    assert "rights_confirmation_required" in source
    assert '/admin/media/{character_id}/replace' in source


def test_media_replacement_is_keyed_by_character_id_not_collection_rows():
    media_db = (ROOT / "database_aninexus_media.py").read_text(encoding="utf-8")

    assert "character_id BIGINT NOT NULL" in media_db
    assert "global_character_images" in media_db
    assert "pg_advisory_xact_lock" in media_db
    assert "user_card_collection" not in media_db


def test_media_history_has_primary_asset_and_rollback():
    media_db = (ROOT / "database_aninexus_media.py").read_text(encoding="utf-8")

    assert "is_primary BOOLEAN" in media_db
    assert "uq_aninexus_character_assets_primary" in media_db
    assert "def activate_asset(" in media_db


def test_remote_images_use_ssrf_safe_fetcher():
    media_service = (ROOT / "utils" / "aninexus_media.py").read_text(encoding="utf-8")

    assert "fetch_public_image" in media_service
    assert "MAX_IMAGE_BYTES" in media_service
    assert "crop_portrait_bytes" in media_service
