from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_bonds_are_persistent_and_transactionally_locked():
    source = _read("database_aninexus_bonds.py")
    assert "CREATE TABLE IF NOT EXISTS aninexus_bonds" in source
    assert "CREATE TABLE IF NOT EXISTS aninexus_bond_invites" in source
    assert "pg_advisory_xact_lock" in source
    assert "FOR UPDATE" in source
    assert "status = 'active'" in source
    assert "INVITE_TTL_DAYS = 7" in source


def test_bond_mutations_acquire_user_locks_before_row_locks():
    source = _read("database_aninexus_bonds.py")
    respond = source.split("def respond_bond_invite", 1)[1].split("def remove_active_bond", 1)[0]
    remove = source.split("def remove_active_bond", 1)[1]

    assert respond.index("_lock_users(cur, inviter_id, invitee_id)") < respond.index("FOR UPDATE")
    assert remove.index("_active_bond_unlocked(cur, user_id)") < remove.index("_lock_users(cur, user_id, preview_other_id)")
    assert remove.index("_lock_users(cur, user_id, preview_other_id)") < remove.index("_active_bond_locked(cur, user_id)")


def test_real_marriage_compatibility_endpoint_comes_from_bond_router():
    router = _read("webapp_routes/aninexus_bonds_duels.py")
    compat = _read("webapp_routes/aninexus_compat.py")
    entry = _read("webapp_entrypoint.py")

    assert '@router.get("/social/marriage")' in router
    assert '@router.get("/social/marriage")' not in compat
    assert "build_aninexus_bonds_duels_router" in entry
    assert "app.include_router(aninexus_bonds_duels_router)" in entry


def test_duel_history_reads_canonical_duels_table():
    source = _read("webapp_routes/aninexus_bonds_duels.py")
    assert '@router.get("/duels/history")' in source
    assert "FROM duels" in source
    assert "challenger_user_id" in source
    assert "challenged_user_id" in source
    assert "winner_user_id" in source
    assert "resolution_reason" in source


def test_duel_stats_remain_backed_by_duel_stats_table():
    source = _read("webapp_routes/aninexus_social.py")
    assert '@router.get("/battle/stats")' in source
    assert "FROM duel_stats" in source
    assert "friendly_wins" in source
    assert "wager_wins" in source
    assert "cards_won" in source


def test_frontend_exposes_duels_and_bonds_as_real_tabs():
    app = _read("aninexus_frontend/src/App.tsx")
    drawer = _read("aninexus_frontend/src/components/NavigationDrawer.tsx")
    assert "./pages/Duels" in app
    assert "./pages/Bonds" in app
    assert "activeTab === 'duels'" in app
    assert "activeTab === 'bonds'" in app
    assert "{ id: 'duels', label: 'Duelos'" in drawer
    assert "{ id: 'bonds', label: 'Vínculos'" in drawer


def test_duel_and_bond_pages_are_native_portuguese():
    duels = _read("aninexus_frontend/src/pages/Duels.tsx")
    bonds = _read("aninexus_frontend/src/pages/Bonds.tsx")
    for expected in (
        "Histórico e desempenho dos seus confrontos",
        "Vitórias",
        "Derrotas",
        "Últimos duelos",
        "Nenhum duelo ainda",
    ):
        assert expected in duels
    for expected in (
        "Vínculos",
        "Enviar convite",
        "Convites recebidos",
        "Encerrar vínculo",
        "Aguardando resposta",
    ):
        assert expected in bonds


def test_remaining_high_visibility_pages_are_native_portuguese():
    achievements = _read("aninexus_frontend/src/pages/Achievements.tsx")
    quests = _read("aninexus_frontend/src/pages/Quests.tsx")
    pets = _read("aninexus_frontend/src/pages/MyPets.tsx")
    pet_modal = _read("aninexus_frontend/src/components/pet/PetActionModal.tsx")

    for forbidden in ("Milestones", "Bragging rights you've earned", "Keep hatching", ">CLEAR<"):
        assert forbidden not in achievements
    for forbidden in ("Mission complete", "No Missions Available", ">Missions</h1>", "DAILY OPERATIONS", "STRATEGIC WEEKLY"):
        assert forbidden not in quests
    for forbidden in (
        ">Companions<",
        ">Active pet<",
        ">All pets<",
        ">Sorted by level<",
        "/> Feed",
        "/> Train",
        "'Active Companion'",
        "'Activate'",
        "No pets yet — visit the Breeder",
    ):
        assert forbidden not in pets
    for forbidden in ("No Image", "PET ID:", "SYSTEM_SUPPORT_PERK", "Set Active", "Active Companion"):
        assert forbidden not in pet_modal
