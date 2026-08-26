from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Every page below calls authenticated APIs using Telegram initData. Keeping this
# list explicit makes a missing SDK include fail CI instead of failing for users.
ACCOUNT_WEBAPPS = [
    "game_webapp.py",
    "collection_webapp.py",
    "profile_webapp.py",
    "ranking_webapp.py",
    "shop_webapp.py",
    "xcards_webapp.py",
    "memory_webapp.py",
    "termo_webapp.py",
    "messages_webapp.py",
    "contrib_webapp.py",
    "hub_webapp.py",
    "agenda_webapp.py",
]


def test_account_webapps_load_telegram_sdk():
    missing = []
    for relative in ACCOUNT_WEBAPPS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        if "telegram.org/js/telegram-web-app.js" not in text:
            missing.append(relative)
    assert not missing, "WebApps sem SDK do Telegram: " + ", ".join(missing)


def test_secure_webapp_dedupes_after_v2_registration():
    text = (ROOT / "secure_webapp.py").read_text(encoding="utf-8")
    register_pos = text.rfind("register_v2_routes(app)")
    dedupe_pos = text.rfind("dedupe_http_routes_keep_last(app)")
    assert register_pos >= 0
    assert dedupe_pos > register_pos, "A deduplicação final precisa acontecer depois do registro V2."
