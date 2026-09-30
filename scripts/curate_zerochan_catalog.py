from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from curate_zerochan_characters import (
    HTTP_RETRIES,
    RETRY_BACKOFF_SECONDS,
    ZEROCHAN_BASE_URL,
    ZerochanClient as BaseZerochanClient,
    curate_character,
    load_characters,
    load_wallhaven,
    normalize,
)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_PATH = ROOT / "data" / "zerochan_character_candidates.json"
STATE_PATH = ROOT / "data" / "zerochan_curation_state.json"
REDIRECT_CODES = {301, 302, 303, 307, 308}
MAX_CANONICAL_REDIRECTS = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _merge_query(url: str, params: dict[str, Any]) -> str:
    parts = urlsplit(str(url))
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        existing[str(key)] = str(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(existing), parts.fragment))


class ZerochanClient(BaseZerochanClient):
    """Zerochan client that preserves ?json across canonical tag redirects.

    Zerochan frequently redirects western-name ordering to its canonical tag
    (e.g. "Akari Kawamoto" -> "Kawamoto Akari"). Its redirect target can drop
    the query string, which silently turns an API request into HTML. The base
    smoke client follows redirects automatically; the catalog client follows
    them manually and re-applies the API query on every hop.
    """

    def __init__(self, username: str, *, delay: float = 1.20, timeout: float = 20.0) -> None:
        super().__init__(username, delay=delay, timeout=timeout)
        self.client.close()
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "User-Agent": f"SourceBaltigo-Zerochan-Curator/0.3 - {self.username}",
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
            },
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = dict(params or {})
        query["json"] = ""
        last_error = ""

        for attempt in range(1, HTTP_RETRIES + 1):
            target = f"{ZEROCHAN_BASE_URL}{path}"
            retry_request = False

            for _redirect in range(MAX_CANONICAL_REDIRECTS + 1):
                self._throttle()
                try:
                    response = self.client.get(_merge_query(target, query))
                    self._last_request = time.monotonic()
                except httpx.RequestError as exc:
                    last_error = f"{type(exc).__name__}:{exc}"
                    retry_request = True
                    break

                if response.status_code in REDIRECT_CODES:
                    location = str(response.headers.get("location") or "").strip()
                    if not location:
                        last_error = "redirect_without_location"
                        retry_request = True
                        break
                    target = urljoin(str(response.url), location)
                    continue

                # A tag that does not exist is a normal search miss, not a
                # transport failure. Returning an empty payload lets the
                # curator try the next tag/name variant.
                if response.status_code == 404:
                    return {}

                if response.status_code == 429:
                    raw_retry = str(response.headers.get("Retry-After") or "5").strip()
                    try:
                        retry_after = max(2.0, min(30.0, float(raw_retry)))
                    except ValueError:
                        retry_after = 5.0
                    last_error = f"rate_limited:{retry_after}"
                    if attempt >= HTTP_RETRIES:
                        raise RuntimeError(f"zerochan_rate_limited:{retry_after}")
                    time.sleep(retry_after)
                    retry_request = True
                    break

                if response.status_code >= 500:
                    last_error = f"http_{response.status_code}"
                    retry_request = True
                    break

                response.raise_for_status()
                try:
                    return response.json()
                except ValueError as exc:
                    content_type = str(response.headers.get("content-type") or "").split(";", 1)[0]
                    preview = re.sub(r"\s+", " ", response.text[:120]).strip()
                    last_error = f"non_json:{response.status_code}:{content_type}:{preview}"
                    if attempt >= HTTP_RETRIES:
                        raise RuntimeError(f"zerochan_non_json:{last_error}") from exc
                    retry_request = True
                    break
            else:
                last_error = "too_many_redirects"
                retry_request = True

            if not retry_request:
                break
            if attempt < HTTP_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        raise RuntimeError(f"zerochan_request_failed:{last_error or 'unknown'}")


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else dict(default)
    except Exception:
        return dict(default)


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _default_candidates() -> dict[str, Any]:
    return {
        "version": 1,
        "source": "zerochan",
        "applies_changes": False,
        "updated_at": None,
        "characters": {},
    }


def _default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "source": "zerochan",
        "updated_at": None,
        "stats": {},
        "processed": {},
    }


def _attempt_count(row: dict[str, Any] | None) -> int:
    try:
        return max(0, int((row or {}).get("attempts") or 0))
    except Exception:
        return 0


def _is_done(row: dict[str, Any] | None, *, max_attempts: int) -> bool:
    if not row:
        return False
    status = str(row.get("status") or "")
    if status in {"approved", "no_match"}:
        return True
    if status == "error" and _attempt_count(row) >= max_attempts:
        return True
    return False


def _candidate_record(character: dict[str, Any], result: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    zerochan_id = int(selected.get("zerochan_id") or 0)
    width = int(selected.get("width") or 0)
    height = int(selected.get("height") or 0)
    ratio = round(width / height, 5) if width > 0 and height > 0 else 0.0
    return {
        "character_id": int(character.get("id") or 0),
        "character_name": str(character.get("name") or ""),
        "anime_id": int(character.get("anime_id") or 0),
        "anime": str(character.get("anime") or ""),
        "anilist_fallback": str(character.get("anilist_image") or ""),
        "url": str(selected.get("full_url") or ""),
        "zerochan_id": zerochan_id,
        "width": width,
        "height": height,
        "ratio": ratio,
        "crop_retention": float(selected.get("crop_retention") or 0.0),
        "score": float(selected.get("score") or 0.0),
        "favorites": int(selected.get("favorites") or 0),
        "official": bool(selected.get("official")),
        "fanart": bool(selected.get("fanart")),
        "solo": bool(selected.get("solo")),
        "primary": str(selected.get("primary") or ""),
        "tags": list(selected.get("tags") or []),
        "reasons": list(selected.get("reasons") or []),
        "source_url": str(selected.get("source_url") or ""),
        "source_page": f"https://www.zerochan.net/{zerochan_id}" if zerochan_id else "",
        "search_tag": str(result.get("search_tag") or ""),
        "approved_at": _now_iso(),
    }


def _state_row(
    character: dict[str, Any],
    *,
    status: str,
    attempts: int,
    result: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    selected = ((result or {}).get("selected") or {}) if isinstance(result, dict) else {}
    return {
        "character_id": int(character.get("id") or 0),
        "character_name": str(character.get("name") or ""),
        "anime_id": int(character.get("anime_id") or 0),
        "anime": str(character.get("anime") or ""),
        "status": str(status),
        "attempts": int(attempts),
        "search_tag": str((result or {}).get("search_tag") or "") if isinstance(result, dict) else "",
        "search_attempts": list((result or {}).get("search_attempts") or []) if isinstance(result, dict) else [],
        "zerochan_id": int(selected.get("zerochan_id") or 0),
        "score": float(selected.get("score") or 0.0),
        "official": bool(selected.get("official")),
        "last_error": str(error or "")[:1000],
        "updated_at": _now_iso(),
    }


def _recompute_stats(state: dict[str, Any], total_characters: int, candidate_count: int) -> dict[str, int]:
    processed = state.get("processed") or {}
    counts = {"approved": 0, "no_match": 0, "error": 0, "other": 0}
    for row in processed.values():
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "other")
        if status not in counts:
            status = "other"
        counts[status] += 1
    finished = counts["approved"] + counts["no_match"] + counts["error"] + counts["other"]
    return {
        "total_characters": int(total_characters),
        "processed_rows": int(finished),
        "approved": int(counts["approved"]),
        "no_match": int(counts["no_match"]),
        "error": int(counts["error"]),
        "other": int(counts["other"]),
        "candidate_records": int(candidate_count),
        "remaining_unseen": max(0, int(total_characters) - int(finished)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resumable Zerochan curator for the complete Source Baltigo character catalog")
    parser.add_argument("--username", default=os.getenv("ZEROCHAN_USERNAME", ""))
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--detail-limit", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--candidates", default=str(CANDIDATES_PATH))
    parser.add_argument("--state", default=str(STATE_PATH))
    parser.add_argument("--checkpoint-every", type=int, default=5)
    args = parser.parse_args()

    username = str(args.username or "").strip()
    if not username:
        print("ERROR ZEROCHAN_USERNAME is required", file=sys.stderr)
        return 2

    batch_size = max(1, min(500, int(args.batch_size)))
    detail_limit = max(1, min(5, int(args.detail_limit)))
    max_attempts = max(1, min(10, int(args.max_attempts)))
    checkpoint_every = max(1, min(50, int(args.checkpoint_every)))
    candidates_path = Path(args.candidates)
    state_path = Path(args.state)

    characters = load_characters()
    wallhaven = load_wallhaven()
    candidates = _load_json(candidates_path, _default_candidates())
    state = _load_json(state_path, _default_state())
    candidate_rows = candidates.setdefault("characters", {})
    processed = state.setdefault("processed", {})

    # First pass prioritizes the 12k+ characters that do not already have a strict Wallhaven override.
    characters.sort(
        key=lambda row: (
            int(row.get("id") or 0) in wallhaven,
            normalize(row.get("anime")),
            normalize(row.get("name")),
            int(row.get("id") or 0),
        )
    )

    queue: list[dict[str, Any]] = []
    for character in characters:
        cid = str(int(character.get("id") or 0))
        row = processed.get(cid) if isinstance(processed.get(cid), dict) else None
        if _is_done(row, max_attempts=max_attempts):
            continue
        queue.append(character)
        if len(queue) >= batch_size:
            break

    print(
        f"CATALOG total={len(characters)} queued={len(queue)} batch_size={batch_size} "
        f"detail_limit={detail_limit} existing_candidates={len(candidate_rows)}",
        flush=True,
    )

    approved_now = 0
    no_match_now = 0
    errors_now = 0
    started = time.monotonic()

    with ZerochanClient(username) as client:
        for index, character in enumerate(queue, start=1):
            cid = str(int(character.get("id") or 0))
            previous = processed.get(cid) if isinstance(processed.get(cid), dict) else None
            attempts = _attempt_count(previous) + 1
            print(
                f"[{index}/{len(queue)}] CHECK id={cid} {character.get('name')} / {character.get('anime')}",
                flush=True,
            )
            try:
                result = curate_character(client, character, detail_limit=detail_limit)
                selected = result.get("selected") or {}
                if selected:
                    candidate_rows[cid] = _candidate_record(character, result, selected)
                    processed[cid] = _state_row(
                        character,
                        status="approved",
                        attempts=attempts,
                        result=result,
                    )
                    approved_now += 1
                    print(
                        f"APPROVED id={cid} zerochan={selected.get('zerochan_id')} "
                        f"score={selected.get('score')} official={selected.get('official')} "
                        f"size={selected.get('width')}x{selected.get('height')}",
                        flush=True,
                    )
                else:
                    processed[cid] = _state_row(
                        character,
                        status="no_match",
                        attempts=attempts,
                        result=result,
                    )
                    no_match_now += 1
                    print(f"NO_MATCH id={cid} rejected={result.get('rejected')}", flush=True)
            except Exception as exc:
                errors_now += 1
                processed[cid] = _state_row(
                    character,
                    status="error",
                    attempts=attempts,
                    error=f"{type(exc).__name__}: {exc}",
                )
                print(f"ERROR id={cid} {type(exc).__name__}: {exc}", flush=True)

            if index % checkpoint_every == 0 or index == len(queue):
                candidates["updated_at"] = _now_iso()
                state["updated_at"] = _now_iso()
                state["stats"] = _recompute_stats(state, len(characters), len(candidate_rows))
                _save_json(candidates_path, candidates)
                _save_json(state_path, state)

    elapsed = round(time.monotonic() - started, 2)
    state["stats"] = _recompute_stats(state, len(characters), len(candidate_rows))
    candidates["updated_at"] = _now_iso()
    state["updated_at"] = _now_iso()
    _save_json(candidates_path, candidates)
    _save_json(state_path, state)

    print(
        "BATCH_SUMMARY "
        + json.dumps(
            {
                "queued": len(queue),
                "approved_now": approved_now,
                "no_match_now": no_match_now,
                "errors_now": errors_now,
                "elapsed_seconds": elapsed,
                "stats": state.get("stats") or {},
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
