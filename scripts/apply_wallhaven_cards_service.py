from pathlib import Path

path = Path("cards_service.py")
text = path.read_text(encoding="utf-8")

anchor = '''CARDS_OVERRIDES_PATH = os.getenv(
    "CARDS_OVERRIDES_PATH",
    os.path.join(DATA_DIR, "cards_overrides.json"),
).strip()
'''
replacement = anchor + '''
WALLHAVEN_CHARACTER_OVERRIDES_PATH = os.getenv(
    "WALLHAVEN_CHARACTER_OVERRIDES_PATH",
    os.path.join(DATA_DIR, "wallhaven_character_overrides.json"),
).strip()
'''
if anchor not in text:
    raise SystemExit("cards overrides path anchor not found")
text = text.replace(anchor, replacement, 1)

anchor = '''def save_cards_overrides(data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    _atomic_write_json(CARDS_OVERRIDES_PATH, data)
    reload_cards_cache()
'''
replacement = '''def load_wallhaven_character_images() -> Dict[int, str]:
    try:
        with open(WALLHAVEN_CHARACTER_OVERRIDES_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}

    characters = raw.get("characters", {}) if isinstance(raw, dict) else {}
    if not isinstance(characters, dict):
        return {}

    out: Dict[int, str] = {}
    for cid_raw, record in characters.items():
        cid = _safe_int(cid_raw)
        if cid is None:
            continue
        if isinstance(record, dict):
            url = str(record.get("url") or "").strip()
        else:
            url = str(record or "").strip()
        if url.startswith("https://"):
            out[int(cid)] = url
    return out


def save_cards_overrides(data: Dict[str, Any]) -> None:
    _ensure_data_dir()
    _atomic_write_json(CARDS_OVERRIDES_PATH, data)
    reload_cards_cache()
'''
if anchor not in text:
    raise SystemExit("save_cards_overrides anchor not found")
text = text.replace(anchor, replacement, 1)

anchor = '''        assets = load_cards_assets_raw()
        overrides = load_cards_overrides()
        db_images_map = get_all_global_character_images()
'''
replacement = '''        assets = load_cards_assets_raw()
        overrides = load_cards_overrides()
        wallhaven_images_map = load_wallhaven_character_images()
        db_images_map = get_all_global_character_images()
'''
if anchor not in text:
    raise SystemExit("build maps anchor not found")
text = text.replace(anchor, replacement, 1)

anchor = '''                db_image = db_images_map.get(cid)
                if db_image:
                    image = str(db_image).strip()
                else:
                    image = overrides["character_image_overrides"].get(
                        str(cid), ch.get("image", "")
                    )
'''
replacement = '''                db_image = str(db_images_map.get(cid) or "").strip()
                manual_image = str(
                    overrides["character_image_overrides"].get(str(cid)) or ""
                ).strip()
                wallhaven_image = str(wallhaven_images_map.get(cid) or "").strip()
                image = (
                    db_image
                    or manual_image
                    or wallhaven_image
                    or str(ch.get("image") or "").strip()
                )
'''
count = text.count(anchor)
if count < 1:
    raise SystemExit("base character image selection anchor not found")
text = text.replace(anchor, replacement, 1)

anchor = '''            db_image = db_images_map.get(cid)
            if db_image:
                image = str(db_image).strip()
            else:
                image = overrides["character_image_overrides"].get(
                    str(cid), str(ch.get("image") or "").strip()
                )
'''
replacement = '''            db_image = str(db_images_map.get(cid) or "").strip()
            manual_image = str(
                overrides["character_image_overrides"].get(str(cid)) or ""
            ).strip()
            wallhaven_image = str(wallhaven_images_map.get(cid) or "").strip()
            image = (
                db_image
                or manual_image
                or wallhaven_image
                or str(ch.get("image") or "").strip()
            )
'''
if anchor not in text:
    raise SystemExit("custom character image selection anchor not found")
text = text.replace(anchor, replacement, 1)

path.write_text(text, encoding="utf-8")
