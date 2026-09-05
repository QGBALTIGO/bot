from __future__ import annotations

import re
import unicodedata
from typing import Any


SEXUAL_TAGS = {
    "bikini", "swimsuit", "underwear", "lingerie", "cleavage", "bathing suit",
    "nude", "naked", "topless", "bottomless", "suggestive", "see through",
    "breasts", "large breasts", "thighhighs", "panties", "wet clothes",
    "shirtless", "shirtless male", "abs", "exposed midriff", "open shirt",
    "bondage", "animal collar", "licking", "tongue", "seductive smile",
}
BAD_TAGS = {
    "scan", "manga page", "screenshot", "comic", "sketch", "monochrome",
    "official art", "text", "multiple persona", "multiple personas", "cosplay",
    "figure", "gender swap", "alternate age", "chibi", "comic panel",
    "watermark", "signature", "lowres", "bad anatomy",
}
ACTION_TAGS = {
    "fight stance", "glow", "glowing eyes", "lightning", "electricity", "fire",
    "wind", "water", "weapon", "weapons", "serious", "looking at camera",
    "dynamic angle", "magic", "special technique", "sharingan", "rinnegan",
}


def _ascii(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def zerochan_queries(name: str) -> list[str]:
    clean = re.sub(r"\s*\([^)]*\)\s*", " ", _ascii(name)).strip()
    parts = clean.split()
    variants = [clean]
    if len(parts) >= 2:
        variants.insert(0, " ".join(parts[-1:] + parts[:-1]))
    aliases = {
        "Minato Namikaze": "Namikaze Minato",
        "Kakashi Hatake": "Hatake Kakashi",
        "Hinata Hyuuga": "Hyuuga Hinata",
        "Sakura Haruno": "Haruno Sakura",
        "Sasuke Uchiha": "Uchiha Sasuke",
        "Itachi Uchiha": "Uchiha Itachi",
        "Boruto Uzumaki": "Uzumaki Boruto",
    }
    if name in aliases:
        variants.insert(0, aliases[name])
    return list(dict.fromkeys(item for item in variants if item))


def score_zerochan_post(post: dict[str, Any]) -> float | None:
    tags = {str(tag).strip().lower() for tag in (post.get("tags") or [])}
    width = int(post.get("width") or 0)
    height = int(post.get("height") or 0)
    if "solo" not in tags or "fanart" not in tags:
        return None
    if tags & SEXUAL_TAGS or tags & BAD_TAGS:
        return None
    if width < 900 or height < 1200:
        return None
    ratio = width / max(1, height)
    # Keep the same safe source window used by the real 2:3 cropper. Wider or
    # extremely tall art would discard too much of the character.
    if ratio < 0.55 or ratio > 0.80:
        return None

    score = min(width * height / 1_000_000, 8.0)
    score += max(0.0, 4.0 - abs(ratio - (2 / 3)) * 8.0)
    score += 3.0 * len(tags & ACTION_TAGS)
    if "behindxa" in tags:
        score += 14.0
    if "fanart from pixiv" in tags or "fanart from x (twitter)" in tags:
        score += 4.0
    if "mobile wallpaper" in tags or "wallpaper" in tags:
        score += 3.0
    if "simple background" in tags:
        score -= 1.5
    return score
