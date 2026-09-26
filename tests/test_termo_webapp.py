from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_termo_webapp_reuses_existing_word_engine_and_tables():
    service = (ROOT / "source_features/termo_web.py").read_text(encoding="utf-8")
    routes = (ROOT / "webapp_routes/aninexus_games.py").read_text(encoding="utf-8")
    ui = (ROOT / "aninexus_frontend/src/components/minigames/TermoAnime.tsx").read_text(encoding="utf-8")
    assert "import commands.termo as termo" in service
    assert "FROM termo_games" in service
    assert "FOR UPDATE" in service
    assert "termo._evaluate" in service
    assert "xp_to_level" in service
    assert '"/termo/start"' in routes
    assert '"/termo/guess"' in routes
    assert "/termo/state" in ui
    assert "/termo/guess" in ui
