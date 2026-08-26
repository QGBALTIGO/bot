from pathlib import Path

path = Path("scripts/curate_wallhaven_characters.py")
text = path.read_text(encoding="utf-8")

anchor = '''def tag_best_match(target: str, tag: dict[str, Any]) -> float:\n    return max((similarity(target, item) for item in variants(tag.get("name"), tag.get("alias"))), default=0.0)\n\n\ndef specific_character_tags(tags: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:\n'''
replacement = '''def tag_best_match(target: str, tag: dict[str, Any]) -> float:\n    return max((similarity(target, item) for item in variants(tag.get("name"), tag.get("alias"))), default=0.0)\n\n\ndef _strip_character_qualifier(value: Any) -> str:\n    # Wallhaven character tags often contain the series in parentheses, e.g.\n    # \"Fern (Sousou No Frieren)\". The qualifier must never participate in\n    # character identity matching, otherwise \"Fern\" can look like\n    # \"Frieren\" only because the series title contains that token.\n    raw = str(value or "").strip()\n    raw = re.sub(r"\\s*[\\(\\[\\{].*?[\\)\\]\\}]\\s*$", "", raw).strip()\n    return raw\n\n\ndef character_tag_variants(tag: dict[str, Any]) -> list[str]:\n    raw_values = [tag.get("name")]\n    raw_values.extend(re.split(r"[,;/|]", str(tag.get("alias") or "")))\n    out: list[str] = []\n    seen: set[str] = set()\n    for raw in raw_values:\n        cleaned = norm(_strip_character_qualifier(raw))\n        if cleaned and cleaned not in seen:\n            seen.add(cleaned)\n            out.append(cleaned)\n    return out\n\n\ndef character_tag_best_match(target: str, tag: dict[str, Any]) -> float:\n    return max((similarity(target, item) for item in character_tag_variants(tag)), default=0.0)\n\n\ndef specific_character_tags(tags: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:\n'''
if anchor not in text:
    raise SystemExit("tag matching anchor not found")
text = text.replace(anchor, replacement, 1)

old = '''    char_match = max((tag_best_match(character_name, x) for x in char_tags), default=0.0)\n    series_match = max((tag_best_match(anime_title, x) for x in series_tags), default=0.0)\n'''
new = '''    char_match = max((character_tag_best_match(character_name, x) for x in char_tags), default=0.0)\n    series_match = max((tag_best_match(anime_title, x) for x in series_tags), default=0.0)\n'''
if old not in text:
    raise SystemExit("char_match anchor not found")
text = text.replace(old, new, 1)

old = '''    other_specific = [x for x in char_tags if tag_best_match(character_name, x) < 0.76]\n'''
new = '''    other_specific = [x for x in char_tags if character_tag_best_match(character_name, x) < 0.76]\n'''
if old not in text:
    raise SystemExit("other_specific anchor not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
