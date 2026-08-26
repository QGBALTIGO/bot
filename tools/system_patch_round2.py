from pathlib import Path


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one exact match, found {count}")
    return text.replace(old, new, 1)


def patch_duel_repository() -> None:
    path = Path("duel_repository.py")
    text = path.read_text(encoding="utf-8")
    text = replace_exact(
        text,
        "from psycopg.rows import dict_row\n",
        "from psycopg import sql\nfrom psycopg.rows import dict_row\n",
        "psycopg sql import",
    )

    old = '''def _update_duel_row(cur, duel_id: int, **fields: Any) -> None:
    if not fields:
        return

    assignments: List[str] = []
    params: List[Any] = []
    for column, value in fields.items():
        assignments.append(f"{column} = %s")
        params.append(value)

    assignments.append("updated_at = NOW()")
    params.append(int(duel_id))
    cur.execute(
        f"UPDATE duels SET {', '.join(assignments)} WHERE duel_id = %s",
        tuple(params),
    )
'''
    new = '''def _update_duel_row(cur, duel_id: int, **fields: Any) -> None:
    if not fields:
        return

    assignments = []
    params: List[Any] = []
    for column, value in fields.items():
        assignments.append(sql.SQL("{} = %s").format(sql.Identifier(str(column))))
        params.append(value)

    assignments.append(sql.SQL("updated_at = NOW()"))
    params.append(int(duel_id))
    query = sql.SQL("UPDATE duels SET {} WHERE duel_id = %s").format(
        sql.SQL(", ").join(assignments)
    )
    cur.execute(query, tuple(params))
'''
    text = replace_exact(text, old, new, "duel dynamic update")
    path.write_text(text, encoding="utf-8")


def patch_xcards() -> None:
    path = Path("xcards_service.py")
    text = path.read_text(encoding="utf-8")
    text = replace_exact(
        text,
        'digest = hashlib.sha1(f"{prefix}:{value}".encode("utf-8")).hexdigest()',
        'digest = hashlib.sha1(\n        f"{prefix}:{value}".encode("utf-8"), usedforsecurity=False\n    ).hexdigest()',
        "non-security sha1 annotation",
    )
    path.write_text(text, encoding="utf-8")


def patch_webapp() -> None:
    path = Path("webapp.py")
    text = path.read_text(encoding="utf-8")

    text = replace_exact(
        text,
        "from fastapi.responses import HTMLResponse, JSONResponse, Response\n",
        "from fastapi.responses import HTMLResponse, JSONResponse, Response\n\nfrom utils.image_proxy import ImageProxyError, fetch_public_image\n",
        "image proxy import",
    )

    route_start = text.find('@app.get("/api/image-proxy")\n')
    route_end = text.find("\n\ndef pick_lang(", route_start)
    if route_start < 0 or route_end < 0:
        raise SystemExit("image proxy route boundaries not found")

    new_route = '''@app.get("/api/image-proxy")
async def api_image_proxy(url: str = Query(..., min_length=8, max_length=2000)):
    target = str(url or "").strip()
    parsed = urlparse(target)
    hostname = (parsed.hostname or "").strip().lower()

    headers = {
        "User-Agent": IMAGE_PROXY_USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

    try:
        content, media_type, _ = await fetch_public_image(
            target,
            headers=headers,
            timeout=httpx.Timeout(20.0, connect=10.0),
        )
    except ImageProxyError as exc:
        print(
            f"[image-proxy] rejected host={hostname or '-'} code={exc.code}",
            flush=True,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except Exception as exc:
        print(
            f"[image-proxy] fetch-failed host={hostname or '-'} error={type(exc).__name__}",
            flush=True,
        )
        raise HTTPException(status_code=502, detail="image_fetch_failed") from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=21600",
            "Access-Control-Allow-Origin": "*",
        },
    )
'''
    text = text[:route_start] + new_route + text[route_end:]

    second_safe_int = "def _safe_int(v: Any, default: int = 0) -> int:\n"
    second_pos = text.find(second_safe_int)
    if second_pos < 0:
        raise SystemExit("Dado _safe_int definition not found")
    if text.find(second_safe_int, second_pos + 1) >= 0:
        raise SystemExit("More than one Dado _safe_int definition found")

    before = text[:second_pos]
    after = text[second_pos:]
    if after.count("_safe_int(") < 1:
        raise SystemExit("No Dado _safe_int references found")
    after = after.replace("_safe_int(", "_dado_safe_int(")
    text = before + after

    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_duel_repository()
    patch_xcards()
    patch_webapp()
