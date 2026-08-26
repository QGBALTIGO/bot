from pathlib import Path

# ------------------------- webapp.py -------------------------
webapp = Path('webapp.py')
text = webapp.read_text(encoding='utf-8')

anchor = 'from utils.image_proxy import ImageProxyError, fetch_public_image\n'
replacement = anchor + 'from utils.portrait_image import PortraitCropError, crop_portrait_bytes\n'
if anchor not in text:
    raise SystemExit('webapp image_proxy import anchor not found')
text = text.replace(anchor, replacement, 1)

old = '''    host = (parsed.hostname or "").strip().lower()
    if host in DIRECT_IMAGE_HOSTS:
        return value

    return f"/api/image-proxy?url={quote(value, safe='')}"
'''
new = '''    host = (parsed.hostname or "").strip().lower()
    if host in DIRECT_IMAGE_HOSTS:
        return value

    encoded = quote(value, safe="")
    if host == "w.wallhaven.cc":
        return f"/api/image-proxy?crop=portrait&url={encoded}"
    return f"/api/image-proxy?url={encoded}"
'''
if old not in text:
    raise SystemExit('webapp _web_image_url anchor not found')
text = text.replace(old, new, 1)

old = '''@app.get("/api/image-proxy")
async def api_image_proxy(url: str = Query(..., min_length=8, max_length=2000)):
'''
new = '''@app.get("/api/image-proxy")
async def api_image_proxy(
    url: str = Query(..., min_length=8, max_length=2000),
    crop: str = Query("", max_length=20),
):
'''
if old not in text:
    raise SystemExit('webapp proxy signature anchor not found')
text = text.replace(old, new, 1)

old = '''    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=21600",
            "Access-Control-Allow-Origin": "*",
        },
    )
'''
new = '''    crop_mode = str(crop or "").strip().lower()
    if crop_mode not in {"", "portrait"}:
        raise HTTPException(status_code=400, detail="invalid_crop_mode")

    applied_crop = False
    if crop_mode == "portrait":
        try:
            content, crop_meta = crop_portrait_bytes(content)
            media_type = "image/jpeg"
            applied_crop = True
        except PortraitCropError as exc:
            print(
                f"[image-proxy] portrait-crop-failed host={hostname or '-'} code={exc}",
                flush=True,
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=604800, stale-while-revalidate=86400",
            "Access-Control-Allow-Origin": "*",
            "X-Image-Crop": "2:3" if applied_crop else "original",
        },
    )
'''
if old not in text:
    raise SystemExit('webapp proxy response anchor not found')
text = text.replace(old, new, 1)
webapp.write_text(text, encoding='utf-8')

# ----------------- scripts/curate_wallhaven_characters.py -----------------
curator = Path('scripts/curate_wallhaven_characters.py')
text = curator.read_text(encoding='utf-8')

text = text.replace(
    'TARGET_RATIO = 2.0 / 3.0\nRATIO_TOLERANCE = 0.045\n',
    'TARGET_RATIO = 2.0 / 3.0\nMIN_SOURCE_RATIO = 0.55\nMAX_SOURCE_RATIO = 0.80\nMIN_CROP_RETENTION = 0.82\n',
    1,
)

anchor = '''def tokens(value: Any) -> set[str]:
    return {x for x in norm(value).split() if len(x) >= 2 and x not in STOP_TOKENS}
'''
replacement = anchor + '''

def crop_retention_for_ratio(ratio: float) -> float:
    value = float(ratio or 0.0)
    if value <= 0:
        return 0.0
    if value >= TARGET_RATIO:
        return TARGET_RATIO / value
    return value / TARGET_RATIO
'''
if anchor not in text:
    raise SystemExit('curator tokens anchor not found')
text = text.replace(anchor, replacement, 1)

old = '''    ratio = width / height if height else 0.0
    ratio_distance = abs(ratio - TARGET_RATIO)
    if ratio_distance > RATIO_TOLERANCE:
        return None
'''
new = '''    ratio = width / height if height else 0.0
    crop_retention = crop_retention_for_ratio(ratio)
    if not (MIN_SOURCE_RATIO <= ratio <= MAX_SOURCE_RATIO):
        return None
    if crop_retention < MIN_CROP_RETENTION:
        return None
'''
if old not in text:
    raise SystemExit('curator evaluate ratio anchor not found')
text = text.replace(old, new, 1)

old = '    ratio_score = max(0.0, 1.0 - ratio_distance / RATIO_TOLERANCE) * 32.0\n'
new = '    ratio_score = crop_retention * 32.0\n'
if old not in text:
    raise SystemExit('curator ratio score anchor not found')
text = text.replace(old, new, 1)

old = '''        "ratio": round(ratio, 5),
        "score": score,
'''
new = '''        "ratio": round(ratio, 5),
        "crop_2x3": True,
        "crop_retention": round(crop_retention, 5),
        "score": score,
'''
if old not in text:
    raise SystemExit('curator return ratio anchor not found')
text = text.replace(old, new, 1)

old = '''    ratio = width / height if height else 0.0
    return abs(ratio - TARGET_RATIO) <= RATIO_TOLERANCE
'''
new = '''    ratio = width / height if height else 0.0
    return (
        MIN_SOURCE_RATIO <= ratio <= MAX_SOURCE_RATIO
        and crop_retention_for_ratio(ratio) >= MIN_CROP_RETENTION
    )
'''
if old not in text:
    raise SystemExit('curator search shape anchor not found')
text = text.replace(old, new, 1)

old = '''        "ratio": "2:3",
        "ratio_tolerance": RATIO_TOLERANCE,
        "min_width": MIN_WIDTH,
'''
new = '''        "output_ratio": "2:3 exact via image proxy crop",
        "source_ratio_min": MIN_SOURCE_RATIO,
        "source_ratio_max": MAX_SOURCE_RATIO,
        "min_crop_retention": MIN_CROP_RETENTION,
        "min_width": MIN_WIDTH,
'''
if old not in text:
    raise SystemExit('curator filters anchor not found')
text = text.replace(old, new, 1)
curator.write_text(text, encoding='utf-8')
