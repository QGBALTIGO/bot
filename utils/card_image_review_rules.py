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


def score_danbooru_post(post: dict[str, Any]) -> float | None:
    raw_tags = " ".join(
        str(post.get(key) or "")
        for key in (
            "tag_string_general",
            "tag_string_character",
            "tag_string_meta",
        )
    )
    tags = {tag.replace("_", " ").lower() for tag in raw_tags.split()}
    width = int(post.get("image_width") or 0)
    height = int(post.get("image_height") or 0)
    if str(post.get("rating") or "").lower() != "g" or "solo" not in tags:
        return None
    if tags & SEXUAL_TAGS or tags & BAD_TAGS:
        return None
    if width < 900 or height < 1200:
        return None
    ratio = width / max(1, height)
    if ratio < 0.55 or ratio > 0.80:
        return None

    score = min(width * height / 1_000_000, 8.0)
    score += max(0.0, 4.0 - abs(ratio - (2 / 3)) * 8.0)
    score += min(max(0, int(post.get("score") or 0)) / 35.0, 10.0)
    score += min(max(0, int(post.get("fav_count") or 0)) / 15.0, 8.0)
    score += 2.0 * len(tags & ACTION_TAGS)
    return score


def identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _ascii(value).casefold())


def work_tags(title: str) -> set[str]:
    key = identity_key(title)
    aliases = {
        "naruto": {"naruto"},
        "narutoshippuuden": {"naruto"},
        "narutoshippuden": {"naruto"},
        "chainsawman": {"chainsaw_man"},
        "onepiece": {"one_piece"},
        "jujutsukaisen": {"jujutsu_kaisen"},
        "kimetsunoyaiba": {"kimetsu_no_yaiba"},
        "demonslayer": {"kimetsu_no_yaiba"},
    }
    return aliases.get(key, {re.sub(r"[^a-z0-9]+", "_", _ascii(title).casefold()).strip("_")})


def matches_danbooru_identity(post: dict[str, Any], name: str, title: str) -> bool:
    characters = str(post.get("tag_string_character") or "").split()
    copyrights = str(post.get("tag_string_copyright") or "").split()
    expected_works = {identity_key(tag) for tag in work_tags(title)}
    # Require one identified character and one matching franchise; ambiguous
    # names and generic tags such as 'beam' must never establish identity.
    if len(characters) != 1 or not copyrights:
        return False
    if not all(identity_key(tag) in expected_works for tag in copyrights):
        return False
    tag = characters[0]
    match = re.fullmatch(r"(.+?)_\((.+)\)", tag)
    if match:
        tag, qualifier = match.groups()
        if identity_key(qualifier) not in expected_works:
            return False
    names = {identity_key(variant) for variant in zerochan_queries(name)}
    return identity_key(tag) in names
