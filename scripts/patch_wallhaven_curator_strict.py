from pathlib import Path

path = Path('scripts/curate_wallhaven_characters.py')
text = path.read_text(encoding='utf-8')

text = text.replace(
'''MAX_CANDIDATES = 3
REQUEST_DELAY = max(0.8, float(os.getenv("WALLHAVEN_CURATOR_DELAY", "1.45")))
''',
'''MAX_CANDIDATES = 4
REQUEST_DELAY = max(0.8, float(os.getenv("WALLHAVEN_CURATOR_DELAY", "1.45")))

SEARCH_ALIASES = {
    40: "Monkey D. Luffy",
    62: "Roronoa Zoro",
    61: "Nico Robin",
    305: "Sanji",
    2072: "Portgas D. Ace",
    16342: "Boa Hancock",
    727: "Shanks",
    13767: "Trafalgar Law",
    5: "Ichigo Kurosaki",
    6: "Rukia Kuchiki",
}
''', 1)

text = text.replace(
'''    "luffy monkey", "zoro roronoa", "nami", "robin nico", "sanji vinsmoke", "ace portgas",
''',
'''    "luffy monkey", "zoro roronoa", "nami", "robin nico", "sanji", "sanji vinsmoke", "ace portgas",
''', 1)

text = text.replace(
'''    other_specific = [x for x in char_tags if tag_best_match(character_name, x) < 0.76]
    if len(other_specific) >= 3:
        return None
''',
'''    other_specific = [x for x in char_tags if tag_best_match(character_name, x) < 0.76]
    # Character portraits must be solo. Any second specific character tag
    # rejects the wallpaper, even when the target character is correct.
    if other_specific:
        return None
''', 1)

text = text.replace(
'''    solo_bonus = 8.0 if not other_specific else max(0.0, 5.0 - 2.5 * len(other_specific))
''',
'''    solo_bonus = 8.0
''', 1)

text = text.replace(
'''def character_priority(name: str) -> int:
    for index, target in enumerate(PRIORITY_CHARACTERS):
        if similarity(name, target) >= 0.76:
            return index
    return len(PRIORITY_CHARACTERS) + 1
''',
'''def character_priority(name: str) -> int:
    name_norm = norm(name)
    name_tokens = tokens(name)
    for index, target in enumerate(PRIORITY_CHARACTERS):
        if name_norm == norm(target) or (name_tokens and name_tokens == tokens(target)):
            return index
    return len(PRIORITY_CHARACTERS) + 1
''', 1)

text = text.replace(
'''    # Search by character only. Series identity is enforced later using the
    # Wallhaven Series tags, which is more reliable for AniList name ordering.
    query = character["name"]
''',
'''    # Search by a canonical alias when AniList stores the name in a form
    # Wallhaven rarely indexes. Series identity is still mandatory in tags.
    query = SEARCH_ALIASES.get(int(character["id"]), character["name"])
''', 1)

text = text.replace(
'''        "max_other_specific_characters": 2,
''',
'''        "max_other_specific_characters": 0,
''', 1)

required = [
    'SEARCH_ALIASES = {',
    'if other_specific:\n        return None',
    'name_tokens == tokens(target)',
    'SEARCH_ALIASES.get(int(character["id"]), character["name"])',
    '"max_other_specific_characters": 0',
]
for marker in required:
    if marker not in text:
        raise SystemExit(f'missing marker after patch: {marker}')

path.write_text(text, encoding='utf-8')

state_path = Path('data/wallhaven_curation_state.json')
if state_path.exists():
    import json
    state = json.loads(state_path.read_text(encoding='utf-8'))
    processed = state.setdefault('processed', {})
    for cid in ('13767', '5'):
        if cid in processed and isinstance(processed[cid], dict):
            processed[cid]['status'] = 'rejected_multi_character'
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
