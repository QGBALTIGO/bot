from __future__ import annotations

import ast
from pathlib import Path


def test_referral_frontend_uses_source_bot_and_does_not_fake_legacy_payouts() -> None:
    text = Path("frontend/src/pages/Referrals.tsx").read_text(encoding="utf-8")
    assert "SourceBaltigo_Bot" in text
    assert "Ganhos v2" in text
    assert "não considera" not in text.lower()  # keep copy concise and explicit elsewhere
    assert "evitando pagamento duplicado retroativo" in text


def test_social_router_uses_central_source_v2_identity() -> None:
    path = Path("webapp_routes/source_v2_social.py")
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    imports = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "utils.source_v2_auth":
            imports.update(alias.name for alias in node.names)

    assert "resolve_source_v2_identity" in imports
    assert "ALLOW_INSECURE_WEBAPP_UID_FALLBACK" not in text


def test_leaderboard_contract_maps_source_metrics_and_respects_private_profiles() -> None:
    text = Path("source_v2_social.py").read_text(encoding="utf-8")
    assert "user_card_collection" in text
    assert "COALESCE(u.coins, 0)" in text
    assert "user_progress" in text
    assert "termo_stats" in text
    assert "profile_visibility" in text
    assert "<> 'private'" in text
    assert 'metric_key == "zenith"' in text
    assert "return []" in text


def test_leaderboard_websocket_requires_signed_source_session() -> None:
    text = Path("webapp_routes/source_v2_social.py").read_text(encoding="utf-8")
    assert "source-token." in text
    assert "validate_session_token(token)" in text
    assert "close(code=4401)" in text
