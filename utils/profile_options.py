from __future__ import annotations

COUNTRY_OPTIONS = [
    {"code": "BR", "flag": "🇧🇷", "name": "Brasil"},
    {"code": "US", "flag": "🇺🇸", "name": "United States"},
    {"code": "ES", "flag": "🇪🇸", "name": "España"},
    {"code": "JP", "flag": "🇯🇵", "name": "日本"},
]

LANGUAGE_OPTIONS = [
    {"code": "pt", "name": "Português"},
    {"code": "en", "name": "English"},
    {"code": "es", "name": "Español"},
]

COUNTRY_CODES = frozenset(str(item["code"]) for item in COUNTRY_OPTIONS)
LANGUAGE_CODES = frozenset(str(item["code"]) for item in LANGUAGE_OPTIONS)
