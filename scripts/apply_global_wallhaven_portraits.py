from pathlib import Path


cards = Path("cards_service.py")
text = cards.read_text(encoding="utf-8")

anchor = "from database import (\n"
import_line = "from utils.public_character_image import character_portrait_url\n\n"
if import_line not in text:
    if anchor not in text:
        raise SystemExit("cards_service import anchor not found")
    text = text.replace(anchor, import_line + anchor, 1)

old = '''                image = (\n                    db_image\n                    or manual_image\n                    or wallhaven_image\n                    or str(ch.get("image") or "").strip()\n                )\n'''
new = '''                image = (\n                    db_image\n                    or manual_image\n                    or character_portrait_url(wallhaven_image)\n                    or str(ch.get("image") or "").strip()\n                )\n'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected 1 standard character image selection, found {count}")
text = text.replace(old, new, 1)

old_custom = '''            image = (\n                db_image\n                or manual_image\n                or wallhaven_image\n                or str(ch.get("image") or "").strip()\n            )\n'''
new_custom = '''            image = (\n                db_image\n                or manual_image\n                or character_portrait_url(wallhaven_image)\n                or str(ch.get("image") or "").strip()\n            )\n'''
count = text.count(old_custom)
if count != 1:
    raise SystemExit(f"expected 1 custom character image selection, found {count}")
text = text.replace(old_custom, new_custom, 1)
cards.write_text(text, encoding="utf-8")


webapp = Path("webapp.py")
text = webapp.read_text(encoding="utf-8")

anchor = "from utils.portrait_image import PortraitCropError, crop_portrait_bytes\n"
import_line = "from utils.public_character_image import is_own_image_proxy_url\n"
if import_line not in text:
    if anchor not in text:
        raise SystemExit("webapp portrait import anchor not found")
    text = text.replace(anchor, anchor + import_line, 1)

old = '''    if value.startswith(("data:", "/api/image-proxy?")):\n        return value\n\n    parsed = urlparse(value)\n'''
new = '''    if value.startswith(("data:", "/api/image-proxy?")):\n        return value\n    if is_own_image_proxy_url(value):\n        return value\n\n    parsed = urlparse(value)\n'''
if old not in text:
    raise SystemExit("webapp _web_image_url pass-through anchor not found")
text = text.replace(old, new, 1)
webapp.write_text(text, encoding="utf-8")
