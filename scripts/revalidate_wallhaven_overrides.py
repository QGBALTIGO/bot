from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from curate_wallhaven_characters import (
    OUTPUT_PATH,
    STATE_PATH,
    RateLimitError,
    evaluate_candidate,
    fetch_detail,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Revalidate stored Wallhaven character portraits")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    output = load_json(OUTPUT_PATH)
    state = load_json(STATE_PATH)
    characters = output.get("characters") or {}
    if not isinstance(characters, dict):
        raise SystemExit("invalid Wallhaven override file")

    api_key = os.getenv("WALLHAVEN_API_KEY", "").strip()
    delay = max(0.8, float(os.getenv("WALLHAVEN_CURATOR_DELAY", "1.45")))
    headers = {"User-Agent": "SourceBaltigo-Wallhaven-Revalidator/1.0"}

    valid = 0
    removed: list[tuple[str, str, str]] = []
    errors: list[tuple[str, str]] = []

    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as client:
        for cid, record in list(characters.items()):
            if not isinstance(record, dict):
                removed.append((cid, "invalid_record", ""))
                if args.apply:
                    characters.pop(cid, None)
                continue

            wid = str(record.get("wallhaven_id") or "").strip()
            name = str(record.get("character_name") or "").strip()
            anime = str(record.get("anime") or "").strip()
            if not wid or not name or not anime:
                removed.append((cid, "missing_identity", wid))
                if args.apply:
                    characters.pop(cid, None)
                continue

            detail = None
            for attempt in range(3):
                try:
                    detail = fetch_detail(client, wid, api_key)
                    break
                except RateLimitError as exc:
                    time.sleep(exc.retry_after)
                except httpx.HTTPError as exc:
                    if attempt >= 2:
                        errors.append((cid, f"{type(exc).__name__}:{exc}"))
                    else:
                        time.sleep(2.5 * (attempt + 1))
            time.sleep(delay)

            if detail is None:
                continue

            checked = evaluate_candidate(detail, name, anime)
            if checked is None:
                tag_names = [
                    str(tag.get("name") or "")
                    for tag in (detail.get("tags") or [])
                    if isinstance(tag, dict) and str(tag.get("category") or "").casefold() == "characters"
                ]
                reason = "strict_validation_failed"
                print(f"REMOVE id={cid} {name} / {anime} wh={wid} tags={tag_names}", flush=True)
                removed.append((cid, reason, wid))
                if args.apply:
                    characters.pop(cid, None)
                    processed = state.setdefault("processed", {})
                    if isinstance(processed, dict):
                        processed[cid] = {
                            "status": "revalidation_failed",
                            "character_name": name,
                            "anime": anime,
                            "wallhaven_id": wid,
                            "checked_at": now_iso(),
                        }
                continue

            valid += 1
            if args.apply:
                preserved = {
                    "character_id": record.get("character_id"),
                    "character_name": name,
                    "anime_id": record.get("anime_id"),
                    "anime": anime,
                    "anilist_fallback": record.get("anilist_fallback", ""),
                    **checked,
                    "query": record.get("query", ""),
                    "approved_at": record.get("approved_at", now_iso()),
                    "revalidated_at": now_iso(),
                }
                characters[cid] = preserved
            print(f"KEEP id={cid} {name} / {anime} wh={wid}", flush=True)

    output["characters"] = characters
    output["revalidated_at"] = now_iso()
    state["revalidated_at"] = now_iso()

    if args.apply:
        OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "SUMMARY",
        json.dumps(
            {
                "valid": valid,
                "removed": len(removed),
                "errors": len(errors),
                "remaining": len(characters),
                "removed_ids": [x[0] for x in removed],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if errors:
        print("ERRORS", errors, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
