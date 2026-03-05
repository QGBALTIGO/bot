import os
import re
import json
import csv
import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple

from telethon import TelegramClient
from telethon.tl.types import Message


RE_YEAR = re.compile(r"(?im)^\s*Ano:\s*(\d{4})\s*\.?\s*$")
RE_STATUS = re.compile(r"(?im)^\s*Status:\s*(.+?)\s*\.?\s*$")
RE_GENRES = re.compile(r"(?im)^\s*Gênero\(s\):\s*(.+?)\s*$")
RE_HASHTAG = re.compile(r"#([A-Za-z0-9_]+)")


def normalize(s: str) -> str:
    return (s or "").replace("\r\n", "\n").strip()


def first_nonempty_line(text: str) -> Optional[str]:
    for line in normalize(text).split("\n"):
        line = line.strip()
        if line:
            return line
    return None


def extract_year(text: str) -> Optional[int]:
    m = RE_YEAR.search(text or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def extract_status(text: str) -> Optional[str]:
    m = RE_STATUS.search(text or "")
    if not m:
        return None
    return m.group(1).strip().rstrip(".")


def extract_genres(text: str) -> List[str]:
    m = RE_GENRES.search(text or "")
    if not m:
        return []
    raw = m.group(1)
    tags = RE_HASHTAG.findall(raw)
    seen = set()
    out = []
    for t in tags:
        key = t.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(t.strip())
    return out


def extract_synopsis(text: str) -> Optional[str]:
    t = normalize(text)
    if "💬" not in t:
        return None
    after = t.split("💬", 1)[1].strip()
    if not after:
        return None
    return after[:900].strip()


def extract_buttons_urls(m: Message) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    rm = getattr(m, "reply_markup", None)
    if not rm:
        return out

    rows = getattr(rm, "rows", None)
    if not rows:
        return out

    for row in rows:
        buttons = getattr(row, "buttons", None)
        if not buttons:
            continue
        for b in buttons:
            url = getattr(b, "url", None)
            if url:
                text = (getattr(b, "text", "") or "").strip()
                out.append((text, url))
    return out


def looks_like_anime_post(text: str) -> bool:
    t = normalize(text)
    title = first_nonempty_line(t)
    if not title or len(title) < 3:
        return False

    signals = 0
    if RE_YEAR.search(t): signals += 1
    if RE_STATUS.search(t): signals += 1
    if RE_GENRES.search(t): signals += 1
    if "💬" in t: signals += 1

    return signals >= 2


def record_from_message(m: Message, channel_username: str) -> Optional[Dict[str, Any]]:
    text = m.message or ""
    if not looks_like_anime_post(text):
        return None

    title = first_nonempty_line(text)
    year = extract_year(text)
    status = extract_status(text)
    genres = extract_genres(text)
    synopsis = extract_synopsis(text)
    buttons = extract_buttons_urls(m)

    main_url = ""
    if buttons:
        chosen = None
        title_low = (title or "").lower()
        for (bt, url) in buttons:
            if bt and title_low and title_low in bt.lower():
                chosen = url
                break
        main_url = chosen or buttons[0][1]

    post_url = f"https://t.me/{channel_username}/{m.id}"

    return {
        "message_id": m.id,
        "date_utc": (m.date.replace(tzinfo=timezone.utc).isoformat() if m.date else None),
        "title": title,
        "year": year,
        "status": status,
        "genres": genres,
        "synopsis": synopsis,
        "main_button_url": main_url,
        "post_url": post_url,
        "button_links": [{"text": t, "url": u} for (t, u) in buttons],
        "raw_text": text,
    }


async def run():
    p = argparse.ArgumentParser()
    p.add_argument("--channel", default="Centraldeanimes_Baltigo")
    p.add_argument("--since-days", type=int, default=0)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out-json", default="channel_index.json")
    p.add_argument("--out-csv", default="channel_index.csv")
    args = p.parse_args()

    api_id = int(os.getenv("TG_API_ID", "0"))
    api_hash = os.getenv("TG_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise RuntimeError("Defina TG_API_ID e TG_API_HASH no ambiente.")

    session_name = os.getenv("TG_SESSION", "session")
    channel = args.channel.strip().lstrip("@")

    since_dt = None
    if args.since_days and args.since_days > 0:
        since_dt = datetime.now(timezone.utc) - timedelta(days=args.since_days)

    client = TelegramClient(session_name, api_id, api_hash)

    records: List[Dict[str, Any]] = []

    async with client:
        async for m in client.iter_messages(channel, limit=(args.limit or None)):
            if not m or not getattr(m, "message", None):
                continue

            if since_dt and m.date:
                md = m.date.replace(tzinfo=timezone.utc)
                if md < since_dt:
                    break

            rec = record_from_message(m, channel)
            if rec:
                records.append(rec)

    records.sort(key=lambda r: r["date_utc"] or "", reverse=True)

    payload = {
        "channel": channel,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "since_days": args.since_days,
        "count": len(records),
        "records": records,
    }

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(args.out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date_utc", "message_id", "title", "year", "status", "genres", "main_button_url", "post_url"])
        for r in records:
            w.writerow([
                r["date_utc"],
                r["message_id"],
                r["title"],
                r.get("year") or "",
                r.get("status") or "",
                ",".join(r.get("genres") or []),
                r.get("main_button_url") or "",
                r.get("post_url") or "",
            ])

    print(f"OK: {len(records)} animes indexados -> {args.out_json} | {args.out_csv}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
