"""Versioned, visually reviewed replacements; later admin edits keep priority."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'naruto_image_curation.v1.json'


def image_source(value: str) -> str:
    value = str(value or '').strip()
    for _ in range(3):
        parsed = urlparse(value)
        if parsed.path != '/api/image-proxy':
            break
        source = parse_qs(parsed.query).get('url', [''])[0]
        if not source or source == value:
            break
        value = source
    return value


def load_reviewed_portraits(path: Path = DEFAULT_PATH) -> dict[int, dict]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload.get('schema') != 'source.reviewed-character-portraits.v1' or payload.get('enabled') is not True:
            return {}
        return {
            int(row['character_id']): row
            for row in payload.get('items', [])
            if row.get('review_status') == 'approved'
            and row.get('anime_id') == 20
            and row.get('previous_image')
            and str(row.get('image', '')).startswith('https://bot-production-1980.up.railway.app/api/image-proxy?')
            and parse_qs(urlparse(row['image']).query).get('crop') == ['portrait']
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}


def apply_reviewed_portrait(character: dict, approved: dict[int, dict]) -> None:
    row = approved.get(int(character.get('id') or 0))
    if not row or character.get('anime_id') != row.get('anime_id'):
        return
    # The baseline is the effective image captured from the production API.
    # A subsequent manual replacement must not be shadowed by this batch.
    if image_source(character.get('image', '')) == image_source(row['previous_image']):
        character['image'] = row['image']
