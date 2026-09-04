from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 ocorrência, encontrado {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, new_block: str, label: str) -> str:
    start_i = text.find(start)
    if start_i < 0:
        raise RuntimeError(f"{label}: início não encontrado")
    end_i = text.find(end, start_i)
    if end_i < 0:
        raise RuntimeError(f"{label}: fim não encontrado")
    return text[:start_i] + new_block + text[end_i:]


# ---------------------------------------------------------------------------
# Jogos: aplicar os bônus reais do companheiro ativo no servidor.
# ---------------------------------------------------------------------------
games_path = Path("database_aninexus_games.py")
games = games_path.read_text(encoding="utf-8")

if "def _pet_modifiers(" not in games:
    games = replace_once(
        games,
        "def _now() -> datetime:\n    return datetime.now(timezone.utc)\n\n\n",
        "def _now() -> datetime:\n    return datetime.now(timezone.utc)\n\n\ndef _pet_modifiers(user_id: int) -> Dict[str, Any]:\n    try:\n        from database_aninexus_pets import active_pet_modifiers\n\n        return dict(active_pet_modifiers(int(user_id)) or {})\n    except Exception:\n        return {\n            \"pet_id\": \"\",\n            \"xp_multiplier\": 1.0,\n            \"bonus_coin_chance\": 0.0,\n            \"energy_bonus\": 0,\n            \"incubation_multiplier\": 1.0,\n            \"egg_drop_chance\": 0.0,\n        }\n\n\ndef _effective_max_energy(user_id: int) -> int:\n    modifiers = _pet_modifiers(int(user_id))\n    return max(1, MAX_ENERGY + max(0, int(modifiers.get(\"energy_bonus\") or 0)))\n\n\n",
        "pet helpers",
    )

energy_block = '''def _ensure_state_locked(cur, user_id: int, max_energy: int) -> Dict[str, Any]:
    max_energy = max(1, int(max_energy))
    cur.execute(
        """
        INSERT INTO aninexus_game_state (user_id, energy, last_energy_recharge)
        VALUES (%s, %s, NOW())
        ON CONFLICT (user_id) DO NOTHING
        """,
        (int(user_id), max_energy),
    )
    cur.execute(
        """
        SELECT user_id, energy, last_energy_recharge
        FROM aninexus_game_state
        WHERE user_id = %s
        FOR UPDATE
        """,
        (int(user_id),),
    )
    return dict(cur.fetchone() or {})


def _refresh_energy_locked(cur, user_id: int, max_energy: int) -> Dict[str, Any]:
    max_energy = max(1, int(max_energy))
    row = _ensure_state_locked(cur, user_id, max_energy)
    raw_energy = max(0, int(row.get("energy") or 0))
    energy = min(max_energy, raw_energy)
    last = row.get("last_energy_recharge")
    now = _now()

    if raw_energy != energy:
        cur.execute(
            """
            UPDATE aninexus_game_state
            SET energy = %s, updated_at = NOW()
            WHERE user_id = %s
            """,
            (energy, int(user_id)),
        )

    if energy >= max_energy:
        return {"energy": max_energy, "last_energy_recharge": None}

    if not isinstance(last, datetime):
        last = now
        cur.execute(
            """
            UPDATE aninexus_game_state
            SET last_energy_recharge = %s, updated_at = NOW()
            WHERE user_id = %s
            """,
            (last, int(user_id)),
        )
        return {"energy": energy, "last_energy_recharge": last}

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    elapsed = max(0.0, (now - last).total_seconds())
    gained = int(elapsed // (RECHARGE_MINUTES * 60))
    if gained <= 0:
        return {"energy": energy, "last_energy_recharge": last}

    new_energy = min(max_energy, energy + gained)
    new_last = last + timedelta(minutes=gained * RECHARGE_MINUTES)
    if new_energy >= max_energy:
        new_last = now

    cur.execute(
        """
        UPDATE aninexus_game_state
        SET energy = %s,
            last_energy_recharge = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (new_energy, new_last, int(user_id)),
    )
    return {
        "energy": new_energy,
        "last_energy_recharge": None if new_energy >= max_energy else new_last,
    }


def get_game_energy(user_id: int) -> Dict[str, Any]:
    _ensure_tables()
    max_energy = _effective_max_energy(int(user_id))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            state = _refresh_energy_locked(cur, int(user_id), max_energy)
            conn.commit()
    last = state.get("last_energy_recharge")
    return {
        "energy": int(state.get("energy") or 0),
        "max_energy": max_energy,
        "last_energy_recharge": last.isoformat() if isinstance(last, datetime) else None,
        "recharge_minutes": RECHARGE_MINUTES,
    }


'''
games = replace_between(
    games,
    "def _ensure_state_locked(",
    "def _wheel_index()",
    energy_block,
    "energy functions",
)

if "max_energy = _effective_max_energy(int(user_id))\n\n    payload = _build_session_payload" not in games:
    games = replace_once(
        games,
        "    if game_type not in {\"cipher_match\", \"nexus_wheel\"}:\n        return {\"ok\": False, \"error\": \"invalid_game\"}\n\n    payload = _build_session_payload(game_type)\n",
        "    if game_type not in {\"cipher_match\", \"nexus_wheel\"}:\n        return {\"ok\": False, \"error\": \"invalid_game\"}\n\n    max_energy = _effective_max_energy(int(user_id))\n    payload = _build_session_payload(game_type)\n",
        "start dynamic max",
    )

games = games.replace(
    "                state = _refresh_energy_locked(cur, int(user_id))\n",
    "                state = _refresh_energy_locked(cur, int(user_id), max_energy)\n",
    1,
)
games = games.replace(
    "                if energy >= MAX_ENERGY or not isinstance(last, datetime):\n",
    "                if energy >= max_energy or not isinstance(last, datetime):\n",
    1,
)

if "pet_modifiers = _pet_modifiers(int(user_id))" not in games:
    games = replace_once(
        games,
        "    if game_type not in {\"cipher_match\", \"nexus_wheel\"} or not session_id:\n        return {\"ok\": False, \"error\": \"invalid_session\"}\n\n    with pool.connection() as conn:\n",
        "    if game_type not in {\"cipher_match\", \"nexus_wheel\"} or not session_id:\n        return {\"ok\": False, \"error\": \"invalid_session\"}\n\n    pet_modifiers = _pet_modifiers(int(user_id))\n\n    with pool.connection() as conn:\n",
        "submit pet modifiers",
    )

modifier_marker = '''                cur.execute(
                    """
                    INSERT INTO users (user_id, coins, created_at, updated_at)
'''
if "bonus_egg = False" not in games:
    games = replace_once(
        games,
        modifier_marker,
        '''                xp_multiplier = max(1.0, float(pet_modifiers.get("xp_multiplier") or 1.0))
                xp = max(1, int(round(xp * xp_multiplier)))

                bonus_coin = False
                bonus_coin_chance = max(0.0, min(1.0, float(pet_modifiers.get("bonus_coin_chance") or 0.0)))
                if bonus_coin_chance > 0 and random.random() < bonus_coin_chance:
                    coins += 1
                    bonus_coin = True

                bonus_egg = False
                egg_drop_chance = max(0.0, min(1.0, float(pet_modifiers.get("egg_drop_chance") or 0.0)))
                if egg_drop_chance > 0 and random.random() < egg_drop_chance:
                    bonus_egg = True

''' + modifier_marker,
        "reward pet modifiers",
    )

old_coin_block = '''                if coins > 0:
                    cur.execute(
                        """
                        UPDATE users
                        SET coins = COALESCE(coins, 0) + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        """,
                        (coins, int(user_id)),
                    )
'''
new_coin_block = '''                if coins > 0:
                    cur.execute(
                        """
                        UPDATE users
                        SET coins = COALESCE(coins, 0) + %s,
                            updated_at = NOW()
                        WHERE user_id = %s
                        RETURNING coins
                        """,
                        (coins, int(user_id)),
                    )
                    balance_after = int((cur.fetchone() or {}).get("coins") or 0)
                    cur.execute(
                        """
                        INSERT INTO shop_transactions
                            (user_id, type, amount, balance_after, metadata)
                        VALUES (
                            %s,
                            'aninexus_game_reward',
                            %s,
                            %s,
                            jsonb_build_object(
                                'game_type', %s,
                                'session_id', %s,
                                'pet_bonus_coin', %s
                            )
                        )
                        """,
                        (
                            int(user_id),
                            coins,
                            balance_after,
                            game_type,
                            session_id,
                            bonus_coin,
                        ),
                    )
'''
if old_coin_block in games:
    games = replace_once(games, old_coin_block, new_coin_block, "coin transaction logging")

if "INSERT INTO aninexus_user_eggs" not in games:
    character_end = '''                        (int(user_id), character_id),
                    )

                reward = {
'''
    games = replace_once(
        games,
        character_end,
        '''                        (int(user_id), character_id),
                    )

                if bonus_egg:
                    cur.execute(
                        """
                        INSERT INTO aninexus_user_eggs (user_id, tier, status, is_corrupted)
                        VALUES (%s, 'common', 'fresh', FALSE)
                        """,
                        (int(user_id),),
                    )

                reward = {
''',
        "bonus egg transaction",
    )

if '"bonus_egg": bonus_egg' not in games:
    games = replace_once(
        games,
        '''                reward = {
                    "shards": coins,
                    "xp": xp,
                    "character": character,
                }
''',
        '''                reward = {
                    "shards": coins,
                    "xp": xp,
                    "character": character,
                    "bonus_egg": bonus_egg,
                }
''',
        "reward bonus egg payload",
    )

games_path.write_text(games, encoding="utf-8")


# ---------------------------------------------------------------------------
# Frontend: drawer, energia e incubação/revelação.
# ---------------------------------------------------------------------------
drawer_path = Path("aninexus_frontend/src/components/NavigationDrawer.tsx")
drawer = drawer_path.read_text(encoding="utf-8")
if "Loja de Companheiros" not in drawer:
    drawer = replace_once(
        drawer,
        "      { id: 'mypets', label: 'Companheiros', icon: PawPrint },\n",
        "      { id: 'mypets', label: 'Companheiros', icon: PawPrint },\n      { id: 'pets', label: 'Loja de Companheiros', icon: Store },\n",
        "pet shop drawer",
    )
drawer_path.write_text(drawer, encoding="utf-8")

energy_path = Path("aninexus_frontend/src/components/minigames/EnergyDisplay.tsx")
energy = energy_path.read_text(encoding="utf-8")
energy = energy.replace(
    "export const ENERGY_RECHARGE_MS = 20 * 60 * 1000; // 20 mins per energy unit",
    "export const ENERGY_RECHARGE_MS = 120 * 60 * 1000; // 2 horas por unidade",
)
energy_path.write_text(energy, encoding="utf-8")

hatchery_path = Path("aninexus_frontend/src/pages/Hatchery.tsx")
hatchery = hatchery_path.read_text(encoding="utf-8")
if "GachaReveal" not in hatchery:
    hatchery = replace_once(
        hatchery,
        "import { Badge } from '../components/ui/Badge';\n",
        "import { Badge } from '../components/ui/Badge';\nimport { GachaReveal } from '../components/ui/GachaReveal';\n",
        "hatch reveal import",
    )
if "revealedChar" not in hatchery:
    hatchery = replace_once(
        hatchery,
        "  const [actionId, setActionId] = useState<string | null>(null);\n  const [now, setNow] = useState<number | null>(null);\n",
        "  const [actionId, setActionId] = useState<string | null>(null);\n  const [now, setNow] = useState<number | null>(null);\n  const [revealedChar, setRevealedChar] = useState<any>(null);\n",
        "hatch reveal state",
    )
    hatchery = replace_once(
        hatchery,
        "      addToast(\n        result?.character?.name ? `Hatched: ${result.character.name}` : 'Egg hatched successfully.',\n        'success',\n      );\n      triggerRefresh();\n",
        "      if (result?.character) {\n        setRevealedChar(result.character);\n        addToast(`${result.character.name} entrou para sua coleção.`, 'success');\n      } else {\n        addToast('Ovo chocado com sucesso.', 'success');\n      }\n      triggerRefresh();\n",
        "hatch reveal action",
    )
    hatchery = replace_once(
        hatchery,
        "      )}\n    </div>\n  );\n};",
        "      )}\n\n      {revealedChar && (\n        <GachaReveal character={revealedChar} onClose={() => setRevealedChar(null)} />\n      )}\n    </div>\n  );\n};",
        "hatch reveal render",
    )

for old, new in {
    "Hatch, fuse and sell your eggs": "Incube, funda e choque seus ovos",
    "Active Slots": "Slot ativo",
    "Access": "Acesso",
    "Fusion — 3× same tier → 1× next tier": "Fusão — 3× do mesmo tipo → 1× do próximo tipo",
    ">Fuse<": ">Fundir<",
    "READY TO HATCH": "PRONTOS PARA CHOCAR",
    "IN PROGRESS": "EM INCUBAÇÃO",
    "NOT INCUBATED": "NÃO INCUBADOS",
    "OTHER": "OUTROS",
    "No eggs yet": "Nenhum ovo ainda",
    "Go hunt with your pet to find eggs.": "Ovos podem ser obtidos por recompensas e habilidades de companheiros.",
    ">Start <": ">Incubar <",
}.items():
    hatchery = hatchery.replace(old, new)
hatchery_path.write_text(hatchery, encoding="utf-8")


# ---------------------------------------------------------------------------
# Traduções adicionais para telas/modais herdados.
# ---------------------------------------------------------------------------
pt_path = Path("aninexus_frontend/src/ptBR.ts")
pt = pt_path.read_text(encoding="utf-8")
anchor = "  'My Pets': 'Meus Companheiros',\n"
extra = """  'Active pet': 'Companheiro ativo',
  'Active Companion': 'Companheiro ativo',
  'All pets': 'Todos os companheiros',
  'Your pets, their levels and bonds': 'Seus companheiros, níveis e vínculos',
  'Sorted by level': 'Ordenados por nível',
  'Vitality': 'Vitalidade',
  'Strike': 'Ataque',
  'Velocity': 'Velocidade',
  'Luck': 'Sorte',
  'Feed': 'Alimentar',
  'Train': 'Treinar',
  'Activate': 'Ativar',
  'No special ability': 'Sem habilidade especial',
  'No Image': 'Sem imagem',
  'Progress': 'Progresso',
  'PET ID:': 'ID DO COMPANHEIRO:',
  'Hatch, fuse and sell your eggs': 'Incube, funda e choque seus ovos',
  'Active Slots': 'Slot ativo',
  'Access': 'Acesso',
  'Start': 'Incubar',
  'Standby': 'Aguardando',
  'Cycle': 'Ciclo',
  'BOOSTED': 'ACELERADO',
  'CORRUPTED': 'CORROMPIDO',
  'READY TO HATCH': 'PRONTOS PARA CHOCAR',
  'IN PROGRESS': 'EM INCUBAÇÃO',
  'NOT INCUBATED': 'NÃO INCUBADOS',
  'OTHER': 'OUTROS',
  'No eggs yet': 'Nenhum ovo ainda',
  'Pet Shop': 'Loja de Companheiros',
  'Breeder': 'Loja de Companheiros',
  'Adopt': 'Adotar',
  'OWNED': 'JÁ POSSUI',
  'Cost': 'Preço',
  'Class': 'Classe',
"""
if "'Active pet': 'Companheiro ativo'" not in pt:
    pt = replace_once(pt, anchor, anchor + extra, "ptBR pet translations")
pt_path.write_text(pt, encoding="utf-8")


# ---------------------------------------------------------------------------
# Limpeza dos nomes técnicos herdados ainda ativos no adaptador.
# ---------------------------------------------------------------------------
compat_path = Path("webapp_routes/aninexus_compat.py")
compat = compat_path.read_text(encoding="utf-8")
compat = compat.replace('tags=["seal-compat"]', 'tags=["aninexus-compat"]')
compat = compat.replace(
    "# Escritas do Seal são bloqueadas até cada subsistema ganhar uma",
    "# Escritas herdadas permanecem bloqueadas até cada subsistema ganhar uma",
)
compat_path.write_text(compat, encoding="utf-8")


# ---------------------------------------------------------------------------
# Exclusão/reset de conta: incluir o novo estado AniNexus.
# ---------------------------------------------------------------------------
db_path = Path("database.py")
db = db_path.read_text(encoding="utf-8")
account_marker = '                cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))\n'
account_cleanup = '''                for table_name in (
                    "aninexus_game_sessions",
                    "aninexus_game_state",
                    "aninexus_quest_claims",
                    "aninexus_pass_claims",
                    "aninexus_user_eggs",
                    "aninexus_user_pets",
                    "aninexus_pet_profiles",
                ):
                    if _optional_table_exists_locked(cur, table_name):
                        cur.execute(f"DELETE FROM {table_name} WHERE user_id = %s", (user_id,))
                if _optional_table_exists_locked(cur, "aninexus_referral_rewards"):
                    cur.execute(
                        "DELETE FROM aninexus_referral_rewards WHERE referred_user_id = %s OR referrer_user_id = %s",
                        (user_id, user_id),
                    )

'''
if "aninexus_game_sessions" not in db[db.find("def delete_user_account"):db.find("def delete_all_users")]:
    db = replace_once(db, account_marker, account_cleanup + account_marker, "account AniNexus cleanup")

reset_marker = '                cur.execute("UPDATE global_character_images SET updated_by = 0")\n'
reset_cleanup = '''                for table_name in (
                    "aninexus_game_sessions",
                    "aninexus_game_state",
                    "aninexus_quest_claims",
                    "aninexus_pass_claims",
                    "aninexus_referral_rewards",
                    "aninexus_user_eggs",
                    "aninexus_user_pets",
                    "aninexus_pet_profiles",
                ):
                    if _optional_table_exists_locked(cur, table_name):
                        cur.execute(f"TRUNCATE TABLE {table_name}")

'''
reset_section = db[db.find("def delete_all_users"):]
if "aninexus_referral_rewards" not in reset_section:
    db = replace_once(db, reset_marker, reset_cleanup + reset_marker, "global reset AniNexus cleanup")

db_path.write_text(db, encoding="utf-8")

print("AniNexus finalization patch applied successfully")
