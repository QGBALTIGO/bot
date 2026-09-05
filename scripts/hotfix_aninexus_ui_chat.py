from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_required(text: str, old: str, new: str, label: str, *, count: int | None = None) -> str:
    found = text.count(old)
    if found == 0:
        raise RuntimeError(f"{label}: trecho não encontrado")
    if count is not None and found != count:
        raise RuntimeError(f"{label}: esperado {count}, encontrado {found}")
    return text.replace(old, new)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise RuntimeError(f"{label}: início não encontrado")
    b = text.find(end, a)
    if b < 0:
        raise RuntimeError(f"{label}: fim não encontrado")
    return text[:a] + replacement + text[b:]


# ---------------------------------------------------------------------------
# Dado: entrega imediata no privado via Bot API, com fila como fallback.
# ---------------------------------------------------------------------------
dado_path = "webapp_routes/aninexus_dado.py"
dado = read(dado_path)
new_delivery = '''def _telegram_bot_call(token: str, method: str, payload: dict[str, Any]) -> bool:
    if not token:
        return False
    try:
        with httpx.Client(timeout=6.0) as client:
            response = client.post(
                f"https://api.telegram.org/bot{token}/{method}",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            return bool(isinstance(body, dict) and body.get("ok"))
    except Exception as exc:
        print(
            f"[dado] entrega direta {method} falhou: {type(exc).__name__}",
            flush=True,
        )
        return False


def _deliver_dado_reward(user_id: int, roll_id: int, character: dict[str, Any]) -> None:
    character_id = int(character.get("id") or 0)
    if character_id <= 0:
        return

    name = escape(str(character.get("name") or "Personagem"))
    anime_title = escape(str(character.get("anime_title") or "Anime"))
    tier = escape(str(character.get("tier") or ""))
    photo = _dado_reward_photo(character_id, str(character.get("image") or ""))
    caption = (
        "🎁 <b>VOCÊ GANHOU!</b>\\n\\n"
        f"🧧 <code>{character_id}</code>. <b>{name}</b>\\n"
        f"<i>{anime_title}</i>\\n"
        + (f"⭐ <b>{tier}</b>\\n" if tier else "")
        + "\\n📦 <b>Adicionado à sua coleção!</b>"
    )

    token = str(os.getenv("BOT_TOKEN", "") or "").strip()
    delivered = False
    if token and photo:
        delivered = _telegram_bot_call(
            token,
            "sendPhoto",
            {
                "chat_id": int(user_id),
                "photo": photo,
                "caption": caption,
                "parse_mode": "HTML",
            },
        )
    if token and not delivered:
        delivered = _telegram_bot_call(
            token,
            "sendMessage",
            {
                "chat_id": int(user_id),
                "text": caption,
                "parse_mode": "HTML",
            },
        )
    if delivered:
        return

    # Persistência de último recurso. Se o processo do bot estiver ativo, o
    # worker consome essa fila; a experiência normal não depende mais dele.
    if not photo:
        return
    try:
        from utils.telegram_outbox import enqueue_photo

        enqueue_photo(
            dedupe_key=f"dado:{int(user_id)}:{int(roll_id)}",
            chat_id=int(user_id),
            photo=photo,
            caption=caption,
            parse_mode="HTML",
        )
    except Exception as exc:
        print(f"[dado] falha ao enfileirar entrega no chat: {type(exc).__name__}", flush=True)


'''
dado = replace_between(
    dado,
    "def _deliver_dado_reward(",
    "def build_aninexus_dado_router()",
    new_delivery,
    "entrega do Dado",
)
dado = replace_required(
    dado,
    "            _deliver_dado_reward(user_id, roll_id, character)\n",
    "            _deliver_dado_reward(\n                user_id,\n                roll_id,\n                {**character, \"tier\": tier[\"tier\"], \"stars\": tier[\"stars\"]},\n            )\n",
    "payload da entrega do Dado",
    count=1,
)
write(dado_path, dado)


# ---------------------------------------------------------------------------
# Catálogo: texto nativamente em pt-BR.
# ---------------------------------------------------------------------------
gallery_path = "aninexus_frontend/src/pages/Gallery.tsx"
gallery = read(gallery_path)
for old, new, label in [
    ("label: 'ID Asc'", "label: 'ID crescente'", "ordenação ID crescente"),
    ("label: 'ID Desc'", "label: 'ID decrescente'", "ordenação ID decrescente"),
    (">Archive</h1>", ">Catálogo</h1>", "título catálogo"),
    ("Every character you've Collected", "Todos os personagens disponíveis no AniNexus", "subtítulo catálogo"),
    ('aria-label="Refresh archive"', 'aria-label="Atualizar catálogo"', "aria atualizar catálogo"),
    ('placeholder="Search characters..."', 'placeholder="Buscar personagens..."', "busca catálogo"),
    ('aria-label="Clear search"', 'aria-label="Limpar busca"', "aria limpar busca"),
    ('aria-label="Filter by rarity"', 'aria-label="Filtrar por raridade"', "aria raridade"),
    (">ALL RARITIES</option>", ">TODAS AS RARIDADES</option>", "raridades catálogo"),
    ('aria-label="Sort options"', 'aria-label="Opções de ordenação"', "aria ordenação"),
    ("{items.length} record{items.length === 1 ? '' : 's'} found", "{items.length} personagem{items.length === 1 ? '' : 's'} encontrado{items.length === 1 ? '' : 's'}", "contador catálogo"),
    ('title="Archive Mismatch"', 'title="Nenhum personagem encontrado"', "vazio catálogo"),
    ('message="Nothing here yet — hatch some eggs first."', 'message="Tente ajustar a busca ou os filtros."', "mensagem vazio catálogo"),
]:
    gallery = replace_required(gallery, old, new, label, count=1)
write(gallery_path, gallery)


# ---------------------------------------------------------------------------
# Estados genéricos e abertura.
# ---------------------------------------------------------------------------
error_path = "aninexus_frontend/src/components/ui/ErrorState.tsx"
error_state = read(error_path)
for old, new, label in [
    ("title = 'Connection failed'", "title = 'Falha na conexão'", "erro título"),
    ("message = 'Could not reach the ANINEXUS server. Check your connection and retry.'", "message = 'Não foi possível acessar o AniNexus. Verifique sua conexão e tente novamente.'", "erro mensagem"),
    ("actionLabel = 'Try again'", "actionLabel = 'Tentar novamente'", "erro ação"),
]:
    error_state = replace_required(error_state, old, new, label, count=1)
write(error_path, error_state)

empty_path = "aninexus_frontend/src/components/ui/EmptyState.tsx"
empty_state = read(empty_path)
empty_state = replace_required(empty_state, "title = 'Empty Sector'", "title = 'Nada por aqui'", "vazio título", count=1)
empty_state = replace_required(empty_state, "message = 'No records found in this sector.'", "message = 'Nenhum registro encontrado.'", "vazio mensagem", count=1)
write(empty_path, empty_state)

intro_path = "aninexus_frontend/src/components/IntroLoading.tsx"
intro = read(intro_path)
for old, new, label in [
    ("const LOADING_STEPS = ['INITIALIZING', 'VERIFYING TELEGRAM', 'LOADING PROFILE'];", "const LOADING_STEPS = ['INICIANDO', 'VERIFICANDO TELEGRAM', 'CARREGANDO PERFIL'];", "etapas abertura"),
    ("if (failed) return 'CONNECTION FAILED';", "if (failed) return 'FALHA NA CONEXÃO';", "abertura falha"),
    ("if (progress >= 100) return 'READY';", "if (progress >= 100) return 'PRONTO';", "abertura pronto"),
    (">\n                S\n              </span>", ">\n                A\n              </span>", "símbolo AniNexus"),
    ("Waifu Collector", "Colecionador de personagens", "submarca abertura"),
    ("Signed in via Telegram", "Conectado via Telegram", "login abertura"),
    ("{failed ? 'FAILED' : progress >= 100 ? 'READY' : 'SYNCING'}", "{failed ? 'FALHA' : progress >= 100 ? 'PRONTO' : 'SINCRONIZANDO'}", "status abertura"),
]:
    intro = replace_required(intro, old, new, label, count=1)
write(intro_path, intro)


# ---------------------------------------------------------------------------
# Modal de companheiros.
# ---------------------------------------------------------------------------
pet_modal_path = "aninexus_frontend/src/components/pet/PetActionModal.tsx"
pet_modal = read(pet_modal_path)
for old, new, label in [
    ('aria-label="Close"', 'aria-label="Fechar"', "fechar pet"),
    ("selectedPet.rarity?.toUpperCase() || 'STANDARD'", "selectedPet.rarity?.toUpperCase() || 'PADRÃO'", "raridade pet padrão"),
    (">\n                  ACTIVE\n                </Badge>", ">\n                  ATIVO\n                </Badge>", "pet ativo badge"),
    ("{isActive ? 'Active Sync' : 'Activate Companion'}", "{isActive ? 'Companheiro ativo' : 'Ativar companheiro'}", "ação pet"),
    ("Visit Breeder", "Visite a Loja de Companheiros", "visitar loja pets"),
    (">\n                    LOCKED\n                  </Badge>", ">\n                    BLOQUEADO\n                  </Badge>", "pet bloqueado"),
]:
    pet_modal = replace_required(pet_modal, old, new, label, count=1)
write(pet_modal_path, pet_modal)


# ---------------------------------------------------------------------------
# Modal de personagem: raridade e status em pt-BR.
# ---------------------------------------------------------------------------
modal_path = "aninexus_frontend/src/components/character/Modal.tsx"
modal = read(modal_path)
modal = replace_required(
    modal,
    "import { cn, FALLBACK_IMAGE, formatNumber } from '../../utils';",
    "import { cleanRarityLabel, cn, FALLBACK_IMAGE, formatNumber } from '../../utils';",
    "import raridade modal",
    count=1,
)
modal = replace_between(
    modal,
    "  const rarityLabel = character.rarity",
    "  const stockLimit =",
    "  const rarityLabel = cleanRarityLabel(character.rarity).toUpperCase();\n",
    "raridade modal",
)
for old, new, label in [
    ('aria-label="Close"', 'aria-label="Fechar"', "fechar personagem"),
    ("rarityLabel || 'STANDARD'", "rarityLabel || 'PADRÃO'", "raridade personagem padrão"),
    (">\n                  OWNED\n                </Badge>", ">\n                  POSSUÍDO\n                </Badge>", "personagem possuído badge"),
    ("value: character.owned ? 'OWNED' : 'NOT OWNED'", "value: character.owned ? 'POSSUÍDO' : 'NÃO POSSUÍDO'", "status posse"),
    ("label: 'SUPPLY'", "label: 'ESTOQUE'", "estoque label"),
    ("? 'DEPLETED'", "? 'ESGOTADO'", "estoque esgotado"),
    (": 'UNLIMITED'", ": 'ILIMITADO'", "estoque ilimitado"),
    ("label: 'PRICE'", "label: 'PREÇO'", "preço label"),
    ("End of Data", "Fim dos dados", "fim dados"),
]:
    modal = replace_required(modal, old, new, label, count=1)
write(modal_path, modal)


# ---------------------------------------------------------------------------
# Ações de personagem.
# ---------------------------------------------------------------------------
action_path = "aninexus_frontend/src/components/character/CharActionModal.tsx"
action = read(action_path)
replacements = [
    ("'Name is required.'", "'O nome é obrigatório.'"),
    ("`Max ${EDIT_TEXT_MAX} characters.`", "`Máximo de ${EDIT_TEXT_MAX} caracteres.`"),
    ("'Invalid control characters.'", "'Caracteres inválidos.'"),
    ("'Source is required.'", "'A obra é obrigatória.'"),
    ("'Rarity is required.'", "'A raridade é obrigatória.'"),
    ("'Unknown rarity class.'", "'Raridade desconhecida.'"),
    ("'Image URL is required.'", "'A URL da imagem é obrigatória.'"),
    ("'URL too long.'", "'URL muito longa.'"),
    ("'Must be an https:// URL.'", "'Use uma URL https://.'"),
    ("'Missing hostname.'", "'Domínio ausente.'"),
    ("'Credentials not allowed.'", "'Credenciais não são permitidas.'"),
    ("'Invalid URL.'", "'URL inválida.'"),
    ("Character Name", "Nome do personagem"),
    ('placeholder="Name..."', 'placeholder="Nome..."'),
    (">\n            Source\n          </span>", ">\n            Anime / obra\n          </span>"),
    ('placeholder="Source..."', 'placeholder="Anime ou obra..."'),
    ("Rarity Class", "Raridade"),
    ('aria-label="Rarity class"', 'aria-label="Raridade"'),
    ("Tier {option.value}:", "Nível {option.value}:"),
    ("Visual Manifest", "Imagem"),
    ('placeholder="Image URL..."', 'placeholder="URL da imagem..."'),
    (">\n          Cancel\n        </Button>", ">\n          Cancelar\n        </Button>"),
    ("Update Character", "Salvar personagem"),
    ("Registry updated.", "Personagem atualizado."),
    ("Character recycled: +", "Personagem reciclado: +"),
    ("Character sold: +", "Personagem vendido: +"),
    ("`Recycle ${selectedChar.name.toUpperCase()} for ${preview.reward} Coins?`", "`Reciclar ${selectedChar.name.toUpperCase()} por ${preview.reward} Coins?`"),
    ("`Sell ${selectedChar.name.toUpperCase()} for Coins?`", "`Vender ${selectedChar.name.toUpperCase()} por Coins?`"),
    ("Modify Records", "Editar personagem"),
    (">\n              DEPLETED\n            </Badge>", ">\n              ESGOTADO\n            </Badge>"),
    ("Prisms Needed", "Dados necessários"),
    ("Insufficient funds", "Saldo insuficiente"),
    ("Summon Character (", "Comprar personagem ("),
    (") Prisms)", ") Dados)"),
    (">\n                Abort\n              </Button>", ">\n                Cancelar\n              </Button>"),
    ("Confirm Summon", "Confirmar compra"),
    (">\n            Recycle\n          </Button>", ">\n            Reciclar\n          </Button>"),
    (">\n            Liquidate\n          </Button>", ">\n            Vender\n          </Button>"),
    (">\n              Confirm\n            </Button>", ">\n              Confirmar\n            </Button>"),
]
for index, (old, new) in enumerate(replacements, start=1):
    if old not in action:
        raise RuntimeError(f"ação personagem #{index}: trecho não encontrado: {old!r}")
    action = action.replace(old, new)
write(action_path, action)


# ---------------------------------------------------------------------------
# Revelações e minijogos.
# ---------------------------------------------------------------------------
gacha_path = "aninexus_frontend/src/components/ui/GachaReveal.tsx"
gacha = read(gacha_path)
gacha = replace_required(
    gacha,
    "import { FALLBACK_IMAGE } from '../../utils';",
    "import { cleanRarityLabel, FALLBACK_IMAGE } from '../../utils';",
    "import raridade gacha",
    count=1,
)
gacha = replace_between(
    gacha,
    "  const rarityLabel = character.rarity",
    "\n\n  return (",
    "  const rarityLabel = cleanRarityLabel(character.rarity).toUpperCase();",
    "raridade gacha",
)
gacha = replace_required(gacha, "Authorize Entry", "Continuar", "botão gacha", count=1)
write(gacha_path, gacha)

reward_path = "aninexus_frontend/src/components/minigames/RewardModal.tsx"
reward = read(reward_path)
reward = replace_required(
    reward,
    "import { haptics } from '../../utils';",
    "import { cleanRarityLabel, haptics } from '../../utils';",
    "import raridade recompensa",
    count=1,
)
for old, new, label in [
    ("Mystery Prize", "Prêmio misterioso", "prêmio misterioso"),
    ("Tap to reveal what you won", "Toque para revelar o que você ganhou", "texto revelar"),
    ("Reveal Prize", "Revelar prêmio", "botão revelar"),
    ("You won!", "Você ganhou!", "ganhou"),
    ("Operational rewards allocated", "Recompensa adicionada à sua conta", "recompensa adicionada"),
    ("{rewards.character.rarity}", "{cleanRarityLabel(rewards.character.rarity).toUpperCase()}", "raridade recompensa"),
    (">\n                    Exp\n                  </span>", ">\n                    XP\n                  </span>", "xp recompensa"),
    ("Confirm & Close", "Confirmar e fechar", "fechar recompensa"),
]:
    reward = replace_required(reward, old, new, label, count=1)
write(reward_path, reward)

cipher_path = "aninexus_frontend/src/components/minigames/CipherMatch.tsx"
cipher = read(cipher_path)
for old, new, label in [
    ("Grid Sync", "Pares encontrados", "memória pares"),
    ("Sync Capacity", "Jogadas restantes", "memória jogadas"),
    (" Left</span>", " restantes</span>", "memória restantes"),
    (">\n          Abort\n        </Button>", ">\n          Sair\n        </Button>", "memória sair topo"),
    ("Sync Failure", "Tentativa encerrada", "memória falha"),
    ("Operational capacity exceeded", "Você atingiu o limite de jogadas", "memória limite"),
    (">\n              Exit\n            </Button>", ">\n              Sair\n            </Button>", "memória sair"),
    ("Submit Progress", "Finalizar partida", "memória finalizar"),
]:
    cipher = replace_required(cipher, old, new, label, count=1)
write(cipher_path, cipher)


# ---------------------------------------------------------------------------
# Guardas de regressão.
# ---------------------------------------------------------------------------
test_path = Path("tests/test_aninexus_ui_chat_hotfix.py")
test_path.write_text(
    '''from pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef _read(path: str) -> str:\n    return (ROOT / path).read_text(encoding="utf-8")\n\n\ndef test_dado_delivers_directly_before_outbox_fallback():\n    source = _read("webapp_routes/aninexus_dado.py")\n    function = source[source.index("def _deliver_dado_reward"):source.index("def build_aninexus_dado_router")]\n    assert "sendPhoto" in function\n    assert "sendMessage" in function\n    assert "response.raise_for_status()" in source\n    assert function.index("_telegram_bot_call") < function.index("enqueue_photo")\n    assert "tier[\\\"tier\\\"]" in source\n\n\ndef test_high_traffic_ui_has_native_portuguese_copy():\n    files = {\n        "gallery": _read("aninexus_frontend/src/pages/Gallery.tsx"),\n        "pet_modal": _read("aninexus_frontend/src/components/pet/PetActionModal.tsx"),\n        "character_modal": _read("aninexus_frontend/src/components/character/Modal.tsx"),\n        "actions": _read("aninexus_frontend/src/components/character/CharActionModal.tsx"),\n        "reward": _read("aninexus_frontend/src/components/minigames/RewardModal.tsx"),\n        "memory": _read("aninexus_frontend/src/components/minigames/CipherMatch.tsx"),\n        "intro": _read("aninexus_frontend/src/components/IntroLoading.tsx"),\n        "error": _read("aninexus_frontend/src/components/ui/ErrorState.tsx"),\n        "empty": _read("aninexus_frontend/src/components/ui/EmptyState.tsx"),\n    }\n    forbidden = (\n        "Archive Mismatch",\n        "ALL RARITIES",\n        "Mystery Prize",\n        "Confirm & Close",\n        "Active Sync",\n        "Activate Companion",\n        "Visit Breeder",\n        "Grid Sync",\n        "Sync Capacity",\n        "Connection failed",\n        "Waifu Collector",\n        "Signed in via Telegram",\n        "End of Data",\n    )\n    joined = "\\n".join(files.values())\n    for phrase in forbidden:\n        assert phrase not in joined\n\n\ndef test_rarity_labels_are_portuguese_in_shared_surfaces():\n    utils = _read("aninexus_frontend/src/utils/index.ts")\n    modal = _read("aninexus_frontend/src/components/character/Modal.tsx")\n    gacha = _read("aninexus_frontend/src/components/ui/GachaReveal.tsx")\n    reward = _read("aninexus_frontend/src/components/minigames/RewardModal.tsx")\n    assert "common: 'Comum'" in utils\n    assert "legendary: 'Lendário'" in utils\n    assert "cleanRarityLabel(character.rarity)" in modal\n    assert "cleanRarityLabel(character.rarity)" in gacha\n    assert "cleanRarityLabel(rewards.character.rarity)" in reward\n\n\ndef test_live_regressions_from_reported_errors_stay_fixed():\n    pets = _read("database_aninexus_pets.py")\n    progression = _read("database_aninexus_progression_source.py")\n    client = _read("aninexus_frontend/src/api/client.ts")\n    ptbr = _read("aninexus_frontend/src/ptBR.ts")\n    assert "jsonb_build_object('pet_id', %s::text)" in pets\n    assert "to_timestamp(" in progression\n    assert "500: 'Erro interno no servidor.'" in client\n    assert "EXACT[core] ?? core" in ptbr\n''',
    encoding="utf-8",
)

print("Hotfix AniNexus de idioma e entrega do Dado aplicado.")
