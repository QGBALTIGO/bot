from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 ocorrência, encontrado {count}")
    return text.replace(old, new, 1)


# Frontend: a aba administrativa passa a usar o painel real de mídia.
app_path = Path("aninexus_frontend/src/App.tsx")
app = app_path.read_text(encoding="utf-8")
app = replace_once(
    app,
    "const Upload = lazy(() => import('./pages/Upload').then((m) => ({ default: m.Upload })));",
    "const Upload = lazy(() => import('./pages/MediaAdmin').then((m) => ({ default: m.MediaAdmin })));",
    "MediaAdmin lazy import",
)
app_path.write_text(app, encoding="utf-8")

drawer_path = Path("aninexus_frontend/src/components/NavigationDrawer.tsx")
drawer = drawer_path.read_text(encoding="utf-8")
drawer = replace_once(
    drawer,
    "{ id: 'upload', label: 'Cadastro', icon: UploadCloud },",
    "{ id: 'upload', label: 'Artes 2:3', icon: UploadCloud },",
    "drawer media label",
)
drawer_path.write_text(drawer, encoding="utf-8")

# Entry point: registra painel de mídia e battle stats real antes da compatibilidade.
entry_path = Path("webapp_entrypoint.py")
entry = entry_path.read_text(encoding="utf-8")
entry = replace_once(
    entry,
    "from webapp_routes.account import router as account_router\n",
    "from webapp_routes.account import router as account_router\nfrom webapp_routes.aninexus_admin_media import build_aninexus_admin_media_router\n",
    "admin media import",
)
entry = replace_once(
    entry,
    "source_v2_router = build_source_v2_router(banner_url=TOP_BANNER_URL)\naninexus_dado_router = build_aninexus_dado_router()\n",
    "source_v2_router = build_source_v2_router(banner_url=TOP_BANNER_URL)\naninexus_admin_media_router = build_aninexus_admin_media_router()\naninexus_dado_router = build_aninexus_dado_router()\n",
    "admin media instance",
)
entry = replace_once(
    entry,
    '        "/api/v1_7b82/economy",\n',
    '        "/api/v1_7b82/economy",\n        "/api/v1_7b82/battle/stats",\n',
    "battle stats registration",
)
media_block = '''    aninexus_admin_media_paths = {
        "/api/v1_7b82/admin/media/search",
        "/api/v1_7b82/admin/media/{character_id}/assets",
        "/api/v1_7b82/admin/media/{character_id}/replace",
        "/api/v1_7b82/admin/media/assets/{asset_id}/activate",
    }
    if not aninexus_admin_media_paths.issubset(registered_paths):
        app.include_router(aninexus_admin_media_router)
        registered_paths.update(aninexus_admin_media_paths)

'''
marker = '''    aninexus_shop_paths = {
'''
entry = replace_once(entry, marker, media_block + marker, "admin media route block")
entry = replace_once(
    entry,
    '        "/api/v1_7b82/social/marriage",\n        "/api/v1_7b82/battle/stats",\n',
    '        "/api/v1_7b82/social/marriage",\n',
    "remove battle compat registration",
)
entry_path.write_text(entry, encoding="utf-8")

# Remove a implementação vazia de battle stats da camada de compatibilidade.
compat_path = Path("webapp_routes/aninexus_compat.py")
compat = compat_path.read_text(encoding="utf-8")
battle_block = '''    @router.get("/battle/stats")
    def battle_stats(authorization: str = Header(default="")):
        try:
            _require_user(authorization)
        except PermissionError as exc:
            return _unauthorized(str(exc))
        return JSONResponse(None)
'''
if battle_block not in compat:
    raise RuntimeError("battle stats fallback não encontrado")
compat = compat.replace(battle_block, "", 1)
compat_path.write_text(compat, encoding="utf-8")

# Se uma conta for apagada, as artes continuam no catálogo, mas a identidade
# de quem fez o upload é removida do histórico.
db_path = Path("database.py")
db = db_path.read_text(encoding="utf-8")
needle = '''                cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
'''
cleanup = '''                if _optional_table_exists_locked(cur, "aninexus_character_assets"):
                    cur.execute(
                        "UPDATE aninexus_character_assets SET uploaded_by = 0 WHERE uploaded_by = %s",
                        (user_id,),
                    )

'''
if cleanup not in db:
    db = replace_once(db, needle, cleanup + needle, "media uploader redaction")
db_path.write_text(db, encoding="utf-8")

print("AniNexus media admin wiring applied")
