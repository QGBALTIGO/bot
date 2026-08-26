from pathlib import Path


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_bot() -> None:
    path = Path("bot.py")
    text = path.read_text(encoding="utf-8")

    old = '''def run_webapp():
    try:
        from webapp import app as web_app
        from utils.terms_membership import install_terms_membership_route

        # Mantém todo o WebApp original da main e substitui somente a rota
        # usada pelo botão "Verificar inscrição" dos Termos.
        install_terms_membership_route(web_app)

        uvicorn.run(
'''
    new = '''def run_webapp():
    try:
        from webapp import app as web_app

        uvicorn.run(
'''
    text = replace_exact(text, old, new, "obsolete Terms route override")

    start_marker = '        app.bot_data["terms_channel_worker"] = asyncio.create_task(\n'
    end_marker = '\n\n    app = (\n'
    start = text.find(start_marker)
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise SystemExit("Terms worker startup block not found")

    replacement = '''        app.bot_data["terms_channel_worker"] = asyncio.create_task(
            channel_verification_worker(app),
            name="terms-channel-verification",
        )

    async def post_shutdown(app: Application):
        task = app.bot_data.pop("terms_channel_worker", None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
'''
    text = text[:start] + replacement + text[end:]

    builder = '        .post_init(post_init)\n        .build()\n'
    replacement_builder = (
        '        .post_init(post_init)\n'
        '        .post_shutdown(post_shutdown)\n'
        '        .build()\n'
    )
    text = replace_exact(text, builder, replacement_builder, "Application builder")
    path.write_text(text, encoding="utf-8")


def patch_bridge() -> None:
    path = Path("utils/channel_verification_bridge.py")
    text = path.read_text(encoding="utf-8")

    if "import threading\n" not in text:
        text = replace_exact(text, "import secrets\n", "import secrets\nimport threading\n", "threading import")

    text = replace_exact(
        text,
        "_SELFTEST_USER_ID = -1\n\n",
        "_SELFTEST_USER_ID = -1\n"
        "_TABLES_READY = False\n"
        "_TABLES_LOCK = threading.Lock()\n"
        "_CLEANUP_LOCK = threading.Lock()\n"
        "_LAST_CLEANUP_MONOTONIC = 0.0\n"
        "_CLEANUP_INTERVAL_SECONDS = 60.0\n\n",
        "bridge globals",
    )

    old_ensure = '''def ensure_channel_verification_tables() -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_TABLE_SQL)
        conn.commit()
'''
    new_ensure = '''def ensure_channel_verification_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return

    with _TABLES_LOCK:
        if _TABLES_READY:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(_TABLE_SQL)
            conn.commit()
        _TABLES_READY = True
'''
    text = replace_exact(text, old_ensure, new_ensure, "bridge schema initializer")

    old_cleanup = '''def _cleanup_old_requests() -> None:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM channel_verification_requests "
                "WHERE created_at < NOW() - INTERVAL '10 minutes'"
            )
        conn.commit()
'''
    new_cleanup = '''def _cleanup_old_requests() -> None:
    global _LAST_CLEANUP_MONOTONIC
    now = time.monotonic()
    if now - _LAST_CLEANUP_MONOTONIC < _CLEANUP_INTERVAL_SECONDS:
        return

    with _CLEANUP_LOCK:
        now = time.monotonic()
        if now - _LAST_CLEANUP_MONOTONIC < _CLEANUP_INTERVAL_SECONDS:
            return
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM channel_verification_requests "
                    "WHERE created_at < NOW() - INTERVAL '10 minutes'"
                )
            conn.commit()
        _LAST_CLEANUP_MONOTONIC = now
'''
    text = replace_exact(text, old_cleanup, new_cleanup, "bridge cleanup")
    path.write_text(text, encoding="utf-8")


def write_gitignore() -> None:
    Path(".gitignore").write_text(
        "__pycache__/\n"
        "*.py[cod]\n"
        ".env\n"
        ".env.*\n"
        "!.env.example\n"
        "*.session\n"
        "*.session-journal\n"
        ".pytest_cache/\n"
        ".ruff_cache/\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    patch_bot()
    patch_bridge()
    write_gitignore()
