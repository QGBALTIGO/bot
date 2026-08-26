from io import BytesIO

from PIL import Image

from utils.portrait_image import (
    crop_portrait_bytes,
    crop_retention_for_ratio,
    is_acceptable_portrait_shape,
)


def make_image(width: int, height: int) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    out = BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()


def test_accepts_nearby_vertical_shapes():
    assert is_acceptable_portrait_shape(1230, 1754)
    assert is_acceptable_portrait_shape(1488, 2256)
    assert is_acceptable_portrait_shape(1448, 2048)
    assert is_acceptable_portrait_shape(1000, 1800)


def test_rejects_shapes_that_need_excessive_crop():
    assert not is_acceptable_portrait_shape(1000, 2100)
    assert not is_acceptable_portrait_shape(1600, 1800)
    assert not is_acceptable_portrait_shape(1920, 1080)


def test_crop_is_exact_two_by_three_without_upscale():
    content, meta = crop_portrait_bytes(make_image(1488, 2256))
    with Image.open(BytesIO(content)) as cropped:
        assert cropped.size == (1488, 2232)
        assert cropped.width * 3 == cropped.height * 2
    assert meta["crop_retention"] > 0.98


def test_large_portrait_is_capped_at_1600_width():
    content, meta = crop_portrait_bytes(make_image(2400, 3600))
    with Image.open(BytesIO(content)) as cropped:
        assert cropped.size == (1600, 2400)
    assert meta["output_width"] == 1600
    assert meta["output_height"] == 2400


def test_crop_retention_tracks_how_much_art_is_kept():
    assert crop_retention_for_ratio(2 / 3) == 1.0
    assert crop_retention_for_ratio(0.55) >= 0.82
    assert crop_retention_for_ratio(0.80) >= 0.82
