from pathlib import Path

path = Path('cards_service.py')
text = path.read_text(encoding='utf-8')

if 'import time\n' not in text:
    text = text.replace('import tempfile\n', 'import tempfile\nimport time\n', 1)

old = '''_LOCK = RLock()
_CACHE: Optional[Dict[str, Any]] = None
'''
new = '''_LOCK = RLock()
_CACHE: Optional[Dict[str, Any]] = None
_CACHE_LOADED_AT: float = 0.0
CARDS_CACHE_TTL_SECONDS = max(5.0, float(os.getenv("CARDS_CACHE_TTL_SECONDS", "60")))
'''
if old in text:
    text = text.replace(old, new, 1)
elif '_CACHE_LOADED_AT:' not in text:
    raise SystemExit('cache globals anchor not found')

old = '''def reload_cards_cache() -> None:
    global _CACHE
    _CACHE = None
'''
new = '''def reload_cards_cache() -> None:
    global _CACHE, _CACHE_LOADED_AT
    _CACHE = None
    _CACHE_LOADED_AT = 0.0
'''
if old in text:
    text = text.replace(old, new, 1)
elif 'global _CACHE, _CACHE_LOADED_AT' not in text:
    raise SystemExit('reload cache anchor not found')

old = '''def build_cards_final_data(force_reload: bool = False) -> Dict[str, Any]:
    global _CACHE

    with _LOCK:
        if _CACHE is not None and not force_reload:
            return _CACHE
'''
new = '''def build_cards_final_data(force_reload: bool = False) -> Dict[str, Any]:
    global _CACHE, _CACHE_LOADED_AT

    with _LOCK:
        now = time.monotonic()
        cache_fresh = (
            _CACHE is not None
            and _CACHE_LOADED_AT > 0
            and (now - _CACHE_LOADED_AT) < CARDS_CACHE_TTL_SECONDS
        )
        if cache_fresh and not force_reload:
            return _CACHE
'''
if old in text:
    text = text.replace(old, new, 1)
elif 'cache_fresh = (' not in text:
    raise SystemExit('build cache anchor not found')

old = '''        _CACHE = {
            "animes_list": animes_list,
'''
new = '''        _CACHE = {
            "animes_list": animes_list,
'''
# Keep the object unchanged; set timestamp just before returning it.
if old not in text:
    raise SystemExit('cache assignment anchor not found')

old_return = '''        return _CACHE


def find_anime'''
new_return = '''        _CACHE_LOADED_AT = time.monotonic()
        return _CACHE


def find_anime'''
if old_return in text:
    text = text.replace(old_return, new_return, 1)
elif '_CACHE_LOADED_AT = time.monotonic()' not in text:
    raise SystemExit('cache return anchor not found')

path.write_text(text, encoding='utf-8')
