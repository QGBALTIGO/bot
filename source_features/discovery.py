"""Optional scene recognition. Fixed provider, no remote URL fetch from user input."""

from __future__ import annotations
import io
import math
from PIL import Image, UnidentifiedImageError
from source_features.errors import FeatureError

MAX_IMAGE = 2 * 1024 * 1024


def prepare_image(raw: bytes):
    if not raw or len(raw) > MAX_IMAGE:
        raise FeatureError("image_size", "Envie uma imagem de até 2 MB.", 400)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 12_000_000:
                raise FeatureError(
                    "image_dimensions", "Imagem grande demais. Reduza a resolução.", 400
                )
            image.seek(0)
            image.thumbnail((1024, 1024))
            out = io.BytesIO()
            image.convert("RGB").save(out, "JPEG", quality=85)
            return (
                out.getvalue()
            )  # strips metadata before sending to the fixed provider
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise FeatureError(
            "invalid_image", "O arquivo não é uma imagem válida.", 400
        ) from exc


def normalize_results(data: dict):
    if not isinstance(data, dict) or not isinstance(data.get("result"), list):
        raise FeatureError(
            "provider_response",
            "O identificador devolveu uma resposta inválida. Tente novamente.",
            502,
        )
    result = []
    for row in data["result"][:5]:
        if not isinstance(row, dict):
            continue
        anilist = row.get("anilist")
        if not isinstance(anilist, dict) or anilist.get("isAdult"):
            continue
        title = anilist.get("title")
        if not isinstance(title, dict):
            continue
        try:
            cid = int(anilist.get("id") or 0)
            confidence = float(row.get("similarity") or 0)
            start = float(row.get("from") or 0)
        except (ValueError, TypeError, OverflowError):
            continue
        if cid <= 0 or not math.isfinite(confidence) or not math.isfinite(start):
            continue
        name = next(
            (
                title[k][:200]
                for k in ("romaji", "english", "native")
                if isinstance(title.get(k), str) and title[k].strip()
            ),
            "Anime identificado",
        )
        episode = row.get("episode")
        result.append(
            {
                "anime_id": cid,
                "title": name,
                "episode": episode
                if isinstance(episode, int)
                and not isinstance(episode, bool)
                and 0 <= episode <= 100000
                else None,
                "similarity": round(max(0, min(1, confidence)) * 100, 1),
                "at_seconds": round(max(0, start), 1),
            }
        )
    return {
        "items": result,
        "notice": "A identificação é aproximada. Confira o título e o episódio antes de usar o resultado.",
    }
