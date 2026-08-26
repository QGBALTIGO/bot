from pathlib import Path

path = Path('scripts/curate_wallhaven_characters.py')
text = path.read_text(encoding='utf-8')

text = text.replace('RATIO_TOLERANCE = 0.035', 'RATIO_TOLERANCE = 0.045', 1)

old = '''def search_candidates(client: httpx.Client, query: str, api_key: str) -> list[dict[str, Any]]:
    params = {
        "q": query,
        "categories": "010",
        "purity": "100",
        "sorting": "relevance",
        "order": "desc",
        "atleast": f"{MIN_WIDTH}x{MIN_HEIGHT}",
        "ratios": "2x3",
        "page": "1",
    }
    if api_key:
        params["apikey"] = api_key
    response = client.get(API_SEARCH, params=params)
    if response.status_code == 429:
        raise RateLimitError(retry_after(response))
    response.raise_for_status()
    payload = response.json()
    return [x for x in ((payload or {}).get("data") or []) if isinstance(x, dict)]
'''
new = '''def _search_shape_ok(item: dict[str, Any]) -> bool:
    width = int(item.get("dimension_x") or 0)
    height = int(item.get("dimension_y") or 0)
    if width < MIN_WIDTH or height < MIN_HEIGHT or width >= height:
        return False
    ratio = width / height if height else 0.0
    return abs(ratio - TARGET_RATIO) <= RATIO_TOLERANCE


def search_candidates(client: httpx.Client, query: str, api_key: str) -> list[dict[str, Any]]:
    # Do not use Wallhaven's ratios=2x3 bucket. It excludes many excellent
    # near-2:3 portraits (e.g. 1488x2256). Fetch high-resolution results and
    # apply our own numeric ratio rule before spending requests on details.
    params = {
        "q": query,
        "categories": "010",
        "purity": "100",
        "sorting": "relevance",
        "order": "desc",
        "atleast": f"{MIN_WIDTH}x{MIN_HEIGHT}",
        "page": "1",
    }
    if api_key:
        params["apikey"] = api_key
    response = client.get(API_SEARCH, params=params)
    if response.status_code == 429:
        raise RateLimitError(retry_after(response))
    response.raise_for_status()
    payload = response.json()
    items = [x for x in ((payload or {}).get("data") or []) if isinstance(x, dict)]
    return [x for x in items if _search_shape_ok(x)]
'''
if old not in text:
    raise SystemExit('search_candidates anchor not found')
text = text.replace(old, new, 1)

# Stronger solo guard for generic group tags that may not be character-specific.
anchor = '''GENERIC_CHARACTER_TAGS = {
    "anime girls", "anime girl", "anime boys", "anime boy", "manga girls", "manga girl",
    "original character", "original characters", "women", "woman", "men", "man",
}
'''
replacement = anchor + '''GROUP_HINTS = {
    "two women", "two men", "two girls", "two boys", "2girls", "2boys",
    "group", "group of people", "couple", "duo", "multiple girls", "multiple boys",
}
'''
if anchor not in text:
    raise SystemExit('generic tags anchor not found')
text = text.replace(anchor, replacement, 1)

anchor = '''    tags = [x for x in (detail.get("tags") or []) if isinstance(x, dict)]
    char_tags = specific_character_tags(tags)
'''
replacement = '''    tags = [x for x in (detail.get("tags") or []) if isinstance(x, dict)]
    all_tag_variants = {
        variant
        for tag in tags
        for variant in variants(tag.get("name"), tag.get("alias"))
    }
    if any(hint in all_tag_variants for hint in GROUP_HINTS):
        return None

    char_tags = specific_character_tags(tags)
'''
if anchor not in text:
    raise SystemExit('tag block anchor not found')
text = text.replace(anchor, replacement, 1)

for marker in ('RATIO_TOLERANCE = 0.045', 'def _search_shape_ok', 'GROUP_HINTS = {', 'if any(hint in all_tag_variants for hint in GROUP_HINTS)'):
    if marker not in text:
        raise SystemExit(f'missing expected marker: {marker}')

path.write_text(text, encoding='utf-8')
