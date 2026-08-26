from __future__ import annotations

import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv(
    "LIVE_WEBAPP_BASE_URL",
    "https://qgbaltigo-bot-production.up.railway.app",
).rstrip("/")

PAGES = [
    "/",
    "/healthz",
    "/hub",
    "/game",
    "/collection",
    "/profile",
    "/ranking",
    "/shop-v2",
    "/memory",
    "/termo",
    "/messages",
    "/contribute",
    "/xcollection",
    "/catalogo",
    "/mangas",
    "/pedido",
    "/baltigoflix",
    "/agenda",
]

PROTECTED_APIS = [
    "/api/v2/game/state",
    "/api/v2/collection",
    "/api/v2/profile",
    "/api/v2/ranking",
    "/api/v2/shop",
    "/api/v2/xcards/state",
    "/api/v2/memory/stats",
    "/api/v2/termo/state",
    "/api/v2/messages/state",
    "/api/v2/contrib/state",
    "/api/v2/ecosystem/state",
    "/api/v2/agenda",
]


def fetch(path: str, timeout: float = 12.0) -> tuple[int, str, str, float]:
    url = BASE_URL + path
    req = Request(
        url,
        headers={
            "User-Agent": "Baltigo-Live-Smoke/1.1 (+GitHub-Actions)",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    started = time.monotonic()
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            elapsed = time.monotonic() - started
            return int(response.status), str(response.headers.get("content-type") or ""), body, elapsed
    except HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        elapsed = time.monotonic() - started
        return int(exc.code), str(exc.headers.get("content-type") or ""), body, elapsed


def main() -> int:
    print(f"LIVE_WEBAPP_BASE_URL={BASE_URL}", flush=True)
    failures: list[str] = []

    print("\n=== PUBLIC PAGES ===", flush=True)
    for path in PAGES:
        try:
            status, content_type, body, elapsed = fetch(path)
            ok = status == 200
            print(
                f"{'PASS' if ok else 'FAIL'} {path:<20} status={status} time={elapsed:.2f}s "
                f"type={content_type!r} bytes_sample={len(body.encode('utf-8'))}",
                flush=True,
            )
            if not ok:
                print(f"  body={body[:700]!r}", flush=True)
                failures.append(f"{path}: HTTP {status}")
        except (URLError, TimeoutError, OSError) as exc:
            print(f"FAIL {path:<20} ERROR {type(exc).__name__}: {exc}", flush=True)
            failures.append(f"{path}: {type(exc).__name__}: {exc}")

    print("\n=== PROTECTED API AUTH BOUNDARY ===", flush=True)
    for path in PROTECTED_APIS:
        try:
            status, content_type, body, elapsed = fetch(path)
            ok = status in {401, 403}
            print(
                f"{'PASS' if ok else 'FAIL'} {path:<30} status={status} time={elapsed:.2f}s "
                f"type={content_type!r} body={body[:260]!r}",
                flush=True,
            )
            if not ok:
                failures.append(f"{path}: expected 401/403 without Telegram auth, got HTTP {status}")
        except (URLError, TimeoutError, OSError) as exc:
            print(f"FAIL {path:<30} ERROR {type(exc).__name__}: {exc}", flush=True)
            failures.append(f"{path}: {type(exc).__name__}: {exc}")

    if failures:
        print("\nLIVE SMOKE FAILURES:", flush=True)
        for item in failures:
            print(f" - {item}", flush=True)
        return 1

    print("\nLIVE SMOKE: every public page returned 200 and protected APIs rejected anonymous access.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
