from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_top_level_function(path: Path, name: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"{path}: expected one {name}, found {len(matches)}")

    node = matches[0]
    start_line = min([node.lineno, *[decorator.lineno for decorator in node.decorator_list]])
    start = start_line - 1
    end = int(node.end_lineno or node.lineno)
    lines = text.splitlines(keepends=True)
    lines[start:end] = [replacement.strip("\n") + "\n"]
    path.write_text("".join(lines), encoding="utf-8")


def patch_webapp() -> None:
    path = ROOT / "webapp.py"
    text = path.read_text(encoding="utf-8")
    anchor = "from utils.public_character_image import is_own_image_proxy_url\n"
    auth_import = (
        anchor
        + "from utils.telegram_webapp_auth import "
        + "TelegramWebAppAuthError, validate_telegram_init_data\n"
    )
    if "from utils.telegram_webapp_auth import" not in text:
        if anchor not in text:
            raise RuntimeError("webapp auth import anchor missing")
        text = text.replace(anchor, auth_import, 1)
        path.write_text(text, encoding="utf-8")

    replace_top_level_function(
        path,
        "verify_telegram_init_data",
        '''
def verify_telegram_init_data(init_data: str) -> dict:
    try:
        validated = validate_telegram_init_data(init_data, BOT_TOKEN)
    except TelegramWebAppAuthError as exc:
        code = str(exc) or "init_data_invalid"
        status_code = 503 if code == "bot_token_missing" else 401
        raise HTTPException(status_code=status_code, detail=code) from exc

    return {
        "user": dict(validated.get("user") or {}),
        "raw": dict(validated.get("raw") or {}),
    }
''',
    )

    replace_top_level_function(
        path,
        "_resolve_webapp_user",
        '''
def _resolve_webapp_user(
    *,
    x_telegram_init_data: str = "",
    uid: Any = None,
    x_webapp_uid: Any = None,
    body_uid: Any = None,
) -> Dict[str, Any]:
    fallback_uid = _coerce_positive_uid(body_uid, uid, x_webapp_uid)

    if x_telegram_init_data:
        data = _get_tg_user(x_telegram_init_data)
        signed_user_id = int(data["user_id"])
        if fallback_uid > 0 and fallback_uid != signed_user_id:
            raise HTTPException(status_code=403, detail="uid_divergente")
        data["auth_mode"] = "telegram_init_data"
        return data

    allow_insecure_fallback = os.getenv(
        "ALLOW_INSECURE_WEBAPP_UID_FALLBACK",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}
    if allow_insecure_fallback and fallback_uid > 0:
        return _build_fallback_webapp_user(fallback_uid)

    raise HTTPException(status_code=401, detail="telegram_init_data_required")
''',
    )

    replace_top_level_function(
        path,
        "api_accept",
        '''
@app.post("/api/terms/accept")
def api_accept(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    try:
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            x_webapp_uid=x_webapp_uid,
            body_uid=payload.get("uid"),
        )
        user_id = int(ctx["user_id"])
        lang = pick_lang(payload.get("lang"))

        create_or_get_user(user_id)
        set_language(user_id, lang)
        accept_terms(user_id, TERMS_VERSION)
        return {"ok": True, "message": TEXTS[lang]["done"]}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[terms] accept failed type={type(exc).__name__}", flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": TEXTS[pick_lang(payload.get("lang"))]["error"]},
            status_code=500,
        )
''',
    )

    replace_top_level_function(
        path,
        "api_decline",
        '''
@app.post("/api/terms/decline")
def api_decline(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    try:
        ctx = _resolve_webapp_user(
            x_telegram_init_data=x_telegram_init_data,
            x_webapp_uid=x_webapp_uid,
            body_uid=payload.get("uid"),
        )
        user_id = int(ctx["user_id"])
        lang = pick_lang(payload.get("lang"))

        create_or_get_user(user_id)
        set_language(user_id, lang)
        return {"ok": True, "message": TEXTS[lang]["no"]}
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[terms] decline failed type={type(exc).__name__}", flush=True)
        traceback.print_exc()
        return JSONResponse(
            {"ok": False, "message": TEXTS[pick_lang(payload.get("lang"))]["error"]},
            status_code=500,
        )
''',
    )

    replace_top_level_function(
        path,
        "api_channel_check",
        '''
@app.post("/api/channel/check")
def api_channel_check(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=(payload or {}).get("uid"),
    )
    user_id = int(ctx["user_id"])

    if not REQUIRED_CHANNEL:
        return {"ok": True}

    try:
        result = wait_for_verification(user_id, timeout_seconds=8.0)
    except Exception as exc:
        print(
            f"[terms-membership] bridge failed user_id={user_id} type={type(exc).__name__}",
            flush=True,
        )
        return JSONResponse(
            {"ok": False, "message": "Não foi possível iniciar a verificação agora."},
            status_code=502,
        )

    if result.get("ok"):
        return {"ok": True}

    status = str(result.get("status") or "")
    if status == "not_member":
        return JSONResponse(
            {"ok": False, "message": "Você ainda não está no canal obrigatório."},
            status_code=403,
        )

    return JSONResponse(
        {"ok": False, "message": str(result.get("message") or "Falha na verificação.")},
        status_code=503 if status == "timeout" else 502,
    )
''',
    )

    replace_top_level_function(
        path,
        "api_menu_profile",
        '''
@app.get("/api/menu/profile")
def api_menu_profile(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    return JSONResponse(_menu_user_payload(int(ctx["user_id"])))
''',
    )

    replace_top_level_function(
        path,
        "api_menu_collection_characters",
        '''
@app.get("/api/menu/collection-characters")
def api_menu_collection_characters(
    uid: int = Query(default=0),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        uid=uid,
        x_webapp_uid=x_webapp_uid,
    )
    return JSONResponse({
        "ok": True,
        "items": _menu_collection_characters(int(ctx["user_id"])),
    })
''',
    )

    replace_top_level_function(
        path,
        "api_menu_nickname",
        '''
@app.post("/api/menu/nickname")
def api_menu_nickname(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])
    nickname = str(payload.get("nickname") or "").strip()

    if not _valid_menu_nickname(nickname):
        return JSONResponse({
            "ok": False,
            "message": "Nickname inválido. Use 4-17 caracteres, começando com letra maiúscula.",
        }, status_code=400)

    result = set_profile_nickname(user_id, nickname)
    if not result.get("ok"):
        error = result.get("error")
        if error == "nickname_locked":
            return JSONResponse({"ok": False, "message": "Você já definiu seu nickname."}, status_code=400)
        if error == "nickname_taken":
            return JSONResponse({"ok": False, "message": "Esse nickname já está em uso."}, status_code=409)
        return JSONResponse({"ok": False, "message": "Não foi possível salvar o nickname."}, status_code=400)

    return {"ok": True}
''',
    )

    replace_top_level_function(
        path,
        "api_menu_favorite",
        '''
@app.post("/api/menu/favorite")
def api_menu_favorite(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])
    try:
        character_id = int(payload.get("character_id") or 0)
    except (TypeError, ValueError):
        character_id = 0
    if character_id <= 0:
        return JSONResponse({"ok": False, "message": "Personagem inválido."}, status_code=400)

    owned_ids = {int(item["id"]) for item in _menu_collection_characters(user_id)}
    if character_id not in owned_ids:
        return JSONResponse({
            "ok": False,
            "message": "Você só pode favoritar personagens da sua coleção.",
        }, status_code=403)

    set_profile_favorite(user_id, character_id)
    return {"ok": True}
''',
    )

    replace_top_level_function(
        path,
        "api_menu_country",
        '''
@app.post("/api/menu/country")
def api_menu_country(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])
    country_code = str(payload.get("country_code") or "BR").strip().upper()

    if country_code not in {country["code"] for country in COUNTRY_OPTIONS}:
        return JSONResponse({"ok": False, "message": "País inválido."}, status_code=400)

    set_profile_country(user_id, country_code)
    return {"ok": True}
''',
    )

    replace_top_level_function(
        path,
        "api_menu_language",
        '''
@app.post("/api/menu/language")
def api_menu_language(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    user_id = int(ctx["user_id"])
    language = str(payload.get("language") or "pt").strip().lower()

    if language not in {"pt", "en", "es"}:
        return JSONResponse({"ok": False, "message": "Idioma inválido."}, status_code=400)

    set_profile_language(user_id, language)
    return {"ok": True}
''',
    )

    replace_top_level_function(
        path,
        "api_menu_privacy",
        '''
@app.post("/api/menu/privacy")
def api_menu_privacy(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    value = payload.get("value")
    if not isinstance(value, bool):
        return JSONResponse({"ok": False, "message": "Valor de privacidade inválido."}, status_code=400)

    set_profile_private(int(ctx["user_id"]), value)
    return {"ok": True}
''',
    )

    replace_top_level_function(
        path,
        "api_menu_notifications",
        '''
@app.post("/api/menu/notifications")
def api_menu_notifications(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    value = payload.get("value")
    if not isinstance(value, bool):
        return JSONResponse({"ok": False, "message": "Valor de notificação inválido."}, status_code=400)

    set_profile_notifications(int(ctx["user_id"]), value)
    return {"ok": True}
''',
    )

    replace_top_level_function(
        path,
        "api_menu_delete_account",
        '''
@app.post("/api/menu/delete-account")
def api_menu_delete_account(
    payload: dict = Body(...),
    x_telegram_init_data: str = Header(default=""),
    x_webapp_uid: str = Header(default=""),
):
    ctx = _resolve_webapp_user(
        x_telegram_init_data=x_telegram_init_data,
        x_webapp_uid=x_webapp_uid,
        body_uid=payload.get("uid"),
    )
    delete_user_account(int(ctx["user_id"]))
    return {"ok": True}
''',
    )

    text = path.read_text(encoding="utf-8")
    old_terms_post = '''  async function postJson(url, payload) {
    const u = new URL(url, window.location.origin);
    u.searchParams.set("_ts", String(Date.now())); // cache-buster forte

    const res = await fetch(u.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
'''
    new_terms_post = '''  async function postJson(url, payload) {
    const u = new URL(url, window.location.origin);
    u.searchParams.set("_ts", String(Date.now()));

    const headers = { "Content-Type": "application/json" };
    if (tg && tg.initData) headers["X-Telegram-Init-Data"] = tg.initData;
    if (uid > 0) headers["X-WebApp-Uid"] = String(uid);

    const res = await fetch(u.toString(), {
      method: "POST",
      headers,
      body: JSON.stringify(payload)
    });
'''
    if old_terms_post not in text:
        raise RuntimeError("terms postJson anchor missing")
    text = text.replace(old_terms_post, new_terms_post, 1)

    old_webhook_secret = '''    received_secret = (
        request.headers.get("x-webhook-secret")
        or request.headers.get("x-cakto-secret")
        or str(payload.get("secret") or "").strip()
    )

    if WEBHOOK_SECRET and received_secret != WEBHOOK_SECRET:
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
'''
    new_webhook_secret = '''    received_secret = str(
        request.headers.get("x-webhook-secret")
        or request.headers.get("x-cakto-secret")
        or payload.get("secret")
        or ""
    ).strip()

    if not WEBHOOK_SECRET:
        return JSONResponse({"ok": False, "error": "webhook_not_configured"}, status_code=503)
    if not received_secret or not hmac.compare_digest(received_secret, WEBHOOK_SECRET):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    payload = dict(payload)
    payload.pop("secret", None)
'''
    if old_webhook_secret not in text:
        raise RuntimeError("webhook secret anchor missing")
    path.write_text(text.replace(old_webhook_secret, new_webhook_secret, 1), encoding="utf-8")


def patch_menu_ui() -> None:
    path = ROOT / "premium_webapp_ui.py"
    text = path.read_text(encoding="utf-8")
    old = '''async function menuGet(url){{ const res = await fetch(url + (url.includes("?") ? "&" : "?") + "_ts=" + Date.now()); const data = await res.json(); if (!res.ok || !data.ok) throw new Error((data && data.message) || "Erro"); return data; }}
async function menuPost(url, payload){{ const res = await fetch(url + "?_ts=" + Date.now(), {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify(payload) }}); const data = await res.json(); if (!res.ok || !data.ok) throw new Error((data && data.message) || "Erro"); return data; }}
'''
    new = '''async function menuGet(url){{ const response = await authJson(url, {{ uid: MENU_UID }}); if (!response.ok || !response.data.ok) throw new Error((response.data && (response.data.message || response.data.detail)) || "Erro"); return response.data; }}
async function menuPost(url, payload){{ const response = await authJson(url, {{ uid: MENU_UID, method: "POST", json: payload }}); if (!response.ok || !response.data.ok) throw new Error((response.data && (response.data.message || response.data.detail)) || "Erro"); return response.data; }}
'''
    if old not in text:
        raise RuntimeError("menu auth anchor missing")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    patch_webapp()
    patch_menu_ui()
    for path in (ROOT / "webapp.py", ROOT / "premium_webapp_ui.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print("Direct WebApp security hardening applied")


if __name__ == "__main__":
    main()
