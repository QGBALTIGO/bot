from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

TARGET_RATIO = 2.0 / 3.0
MIN_SOURCE_RATIO = 0.55
MAX_SOURCE_RATIO = 0.80
MIN_CROP_RETENTION = 0.82
MAX_OUTPUT_WIDTH = 1600
JPEG_QUALITY = 91


class PortraitCropError(ValueError):
    pass


def crop_retention_for_ratio(ratio: float) -> float:
    value = float(ratio or 0.0)
    if value <= 0:
        return 0.0
    if value >= TARGET_RATIO:
        return TARGET_RATIO / value
    return value / TARGET_RATIO


def is_acceptable_portrait_shape(width: int, height: int) -> bool:
    width = int(width or 0)
    height = int(height or 0)
    if width <= 0 or height <= 0 or width >= height:
        return False
    ratio = width / height
    return (
        MIN_SOURCE_RATIO <= ratio <= MAX_SOURCE_RATIO
        and crop_retention_for_ratio(ratio) >= MIN_CROP_RETENTION
    )


def crop_portrait_bytes(content: bytes) -> tuple[bytes, dict[str, float | int]]:
    if not content:
        raise PortraitCropError("empty_image")

    try:
        with Image.open(BytesIO(content)) as source:
            if getattr(source, "is_animated", False):
                source.seek(0)
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception as exc:
        raise PortraitCropError("invalid_image") from exc

    width, height = image.size
    if not is_acceptable_portrait_shape(width, height):
        raise PortraitCropError("unsupported_portrait_shape")

    source_ratio = width / height
    retention = crop_retention_for_ratio(source_ratio)

    if source_ratio > TARGET_RATIO:
        crop_width = max(1, int(round(height * TARGET_RATIO)))
        left = max(0, (width - crop_width) // 2)
        box = (left, 0, min(width, left + crop_width), height)
    else:
        crop_height = max(1, int(round(width / TARGET_RATIO)))
        vertical_excess = max(0, height - crop_height)
        # Anime portrait framing usually keeps faces above the geometric center.
        # Crop a little more from the bottom than the top to preserve hair/headroom.
        top = int(round(vertical_excess * 0.32))
        top = max(0, min(top, height - crop_height))
        box = (0, top, width, min(height, top + crop_height))

    cropped = image.crop(box)
    output_width = min(MAX_OUTPUT_WIDTH, cropped.width)
    output_height = int(round(output_width / TARGET_RATIO))
    if cropped.size != (output_width, output_height):
        cropped = cropped.resize((output_width, output_height), Image.Resampling.LANCZOS)

    output = BytesIO()
    cropped.save(
        output,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )

    return output.getvalue(), {
        "source_width": width,
        "source_height": height,
        "source_ratio": round(source_ratio, 6),
        "crop_retention": round(retention, 6),
        "output_width": output_width,
        "output_height": output_height,
        "output_ratio": round(output_width / output_height, 6),
    }
