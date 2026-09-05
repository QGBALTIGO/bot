from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1 ocorrência, encontrado {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1. Pets: PostgreSQL precisa do tipo explícito dentro de jsonb_build_object.
# ---------------------------------------------------------------------------
pets_path = "database_aninexus_pets.py"
pets = read(pets_path)
raw_patterns = [
    "jsonb_build_object('pet_id',%s)",
    "jsonb_build_object('pet_id', %s)",
]
replaced = 0
for pattern in raw_patterns:
    count = pets.count(pattern)
    if count:
        pets = pets.replace(pattern, "jsonb_build_object('pet_id', %s::text)")
        replaced += count
if replaced < 2:
    raise RuntimeError(f"pets jsonb cast: esperado corrigir ao menos 2 ocorrências, corrigidas {replaced}")
if "jsonb_build_object('pet_id',%s)" in pets or "jsonb_build_object('pet_id', %s)" in pets:
    raise RuntimeError("pets jsonb cast: ainda existe parâmetro sem tipo")
write(pets_path, pets)


# ---------------------------------------------------------------------------
# 2. Missões: dice_rolls.created_at é Unix BIGINT no banco legado.
#    Aceita segundos e milissegundos sem mudar o schema atual.
# ---------------------------------------------------------------------------
progression_path = "database_aninexus_progression_source.py"
progression = read(progression_path)
progression = replace_once(
    progression,
    """                    SELECT COUNT(*) AS total
                    FROM dice_rolls
                    WHERE user_id = %s AND created_at >= %s
""",
    """                    SELECT COUNT(*) AS total
                    FROM dice_rolls
                    WHERE user_id = %s
                      AND to_timestamp(
                            CASE
                                WHEN created_at > 100000000000
                                    THEN created_at::double precision / 1000.0
                                ELSE created_at::double precision
                            END
                          ) >= %s
""",
    "dice_rolls unix timestamp",
)
write(progression_path, progression)


# ---------------------------------------------------------------------------
# 3. Dado: restaurar entrega da carta no chat do Telegram após commit no banco.
# ---------------------------------------------------------------------------
dado_path = "webapp_routes/aninexus_dado.py"
dado = read(dado_path)
if "from html import escape" not in dado:
    dado = replace_once(
        dado,
        "import json\nimport random\n",
        "import json\nimport os\nimport random\nfrom html import escape\n\nimport httpx\n",
        "dado imports",
    )

helper_marker = "\ndef build_aninexus_dado_router() -> APIRouter:\n"
if "def _deliver_dado_reward(" not in dado:
    helper = r'''

def _dado_reward_photo(character_id: int, web_image: str) -> str:
    try:
        data = build_cards_final_data()
        item = dict((data.get("characters_by_id") or {}).get(int(character_id)) or {})
        raw = str(item.get("image") or "").strip()
        if raw.startswith(("http://", "https://")):
            return raw
    except Exception:
        pass

    image = str(web_image or "").strip()
    base_url = (str(os.getenv("BASE_URL", "") or "").strip() or str(os.getenv("WEBAPP_URL", "") or "").strip()).rstrip("/")
    if image.startswith("/") and base_url:
        return f"{base_url}{image}"
    if image.startswith(("http://", "https://")):
        return image
    return str(os.getenv("DADO_BANNER_URL", "") or "").strip()


def _deliver_dado_reward(user_id: int, roll_id: int, character: dict[str, Any]) -> None:
    character_id = int(character.get("id") or 0)
    if character_id <= 0:
        return

    name = escape(str(character.get("name") or "Personagem"))
    anime_title = escape(str(character.get("anime_title") or "Anime"))
    photo = _dado_reward_photo(character_id, str(character.get("image") or ""))
    caption = (
        "🎁 <b>VOCÊ GANHOU!</b>\n\n"
        f"🧧 <code>{character_id}</code>. <b>{name}</b>\n"
        f"<i>{anime_title}</i>\n\n"
        "📦 <b>Adicionado à sua coleção!</b>"
    )

    try:
        from utils.telegram_outbox import enqueue_photo

        enqueue_photo(
            dedupe_key=f"dado:{int(user_id)}:{int(roll_id)}",
            chat_id=int(user_id),
            photo=photo,
            caption=caption,
            parse_mode="HTML",
        )
        return
    except Exception as exc:
        print(f"[dado] falha ao enfileirar entrega no chat: {type(exc).__name__}", flush=True)

    token = str(os.getenv("BOT_TOKEN", "") or "").strip()
    if not token:
        return
    try:
        with httpx.Client(timeout=8.0) as client:
            if photo:
                client.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    json={
                        "chat_id": int(user_id),
                        "photo": photo,
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                )
            else:
                client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": int(user_id),
                        "text": caption,
                        "parse_mode": "HTML",
                    },
                )
    except Exception as exc:
        print(f"[dado] falha no fallback de entrega: {type(exc).__name__}", flush=True)
'''
    dado = replace_once(dado, helper_marker, helper + helper_marker, "dado reward helper")

notify_anchor = """        tier = _deterministic_tier(
            int(roll_row.get("dice_value") or 1),
            int(character.get("id") or 0),
        )
        return JSONResponse(
"""
if "_deliver_dado_reward(user_id, roll_id, character)" not in dado:
    dado = replace_once(
        dado,
        notify_anchor,
        """        tier = _deterministic_tier(
            int(roll_row.get("dice_value") or 1),
            int(character.get("id") or 0),
        )
        if not already_done:
            _deliver_dado_reward(user_id, roll_id, character)
        return JSONResponse(
""",
        "dado chat delivery",
    )
write(dado_path, dado)


# ---------------------------------------------------------------------------
# 4. Cliente API: mensagens de erro em português, inclusive 500 texto puro.
# ---------------------------------------------------------------------------
client_path = "aninexus_frontend/src/api/client.ts"
client = read(client_path)
for old, new in {
    "return 'Something went wrong. Please try again.';": "return 'Algo deu errado. Tente novamente.';",
    "message: 'Invalid JSON response from server.',": "message: 'Resposta inválida do servidor.',",
    "message: timedOut ? 'Request timed out. Please try again.' : 'Request cancelled.',": "message: timedOut ? 'A solicitação demorou demais. Tente novamente.' : 'Solicitação cancelada.',",
    "message: 'Network connection failed. Check your connection and try again.',": "message: 'Falha de conexão. Verifique sua internet e tente novamente.',",
    "message: 'Session expired. Please reopen the app.',": "message: 'Sessão expirada. Reabra a MiniApp.',",
}.items():
    if old in client:
        client = client.replace(old, new)

client = replace_once(
    client,
    """function buildApiError(response: Response, payload: unknown) {
  const status = response.status;
  let message = response.statusText || `API error: ${status}`;
""",
    """function buildApiError(response: Response, payload: unknown) {
  const status = response.status;
  const statusMessages: Record<number, string> = {
    400: 'Solicitação inválida.',
    401: 'Sessão expirada. Reabra a MiniApp.',
    403: 'Acesso negado.',
    404: 'Recurso não encontrado.',
    409: 'A operação não pôde ser concluída.',
    429: 'Muitas tentativas. Aguarde um pouco.',
    500: 'Erro interno no servidor.',
    502: 'Serviço temporariamente indisponível.',
    503: 'Serviço temporariamente indisponível.',
  };
  let message = statusMessages[status] || `Erro da API: ${status}`;
""",
    "api status messages",
)
client = replace_once(
    client,
    """  return new ApiError({
    message,
    status,
""",
    """  if (message === 'Internal Server Error') message = 'Erro interno no servidor.';
  if (message === 'Bad Gateway') message = 'Serviço temporariamente indisponível.';
  if (message === 'Service Unavailable') message = 'Serviço temporariamente indisponível.';

  return new ApiError({
    message,
    status,
""",
    "api raw status localization",
)
write(client_path, client)


# ---------------------------------------------------------------------------
# 5. Tradutor: frases inteiras, nunca pedaços de palavras (Rank -> PosiçãoING).
# ---------------------------------------------------------------------------
pt_path = "aninexus_frontend/src/ptBR.ts"
pt = read(pt_path)
extra_entries = """  'Internal Server Error': 'Erro interno no servidor.',
  'INTERNAL SERVER ERROR': 'ERRO INTERNO NO SERVIDOR',
  'Incubation started.': 'Incubação iniciada.',
  'INCUBATION STARTED.': 'INCUBAÇÃO INICIADA.',
  'Your collection': 'Sua coleção',
  'YOUR COLLECTION': 'SUA COLEÇÃO',
  \"Every waifu you've collected\": 'Todos os personagens que você já coletou',
  \"EVERY WAIFU YOU'VE COLLECTED\": 'TODOS OS PERSONAGENS QUE VOCÊ JÁ COLETOU',
  'Search characters...': 'Buscar personagens...',
  'ALL RARITIES': 'TODAS AS RARIDADES',
  'Refresh collection': 'Atualizar coleção',
  'Filter by rarity': 'Filtrar por raridade',
  'Nothing here yet': 'Nada por aqui ainda',
  'Hatch some eggs to start your collection.': 'Use o Dado, jogos e ovos para aumentar sua coleção.',
  'Egg sold.': 'Ovo vendido.',
  'Egg purified.': 'Ovo purificado.',
  'Eggs fused.': 'Ovos fundidos.',
  'Ready': 'Prontos',
  'hidden': 'ocultos',
"""
if "'Internal Server Error': 'Erro interno no servidor.'" not in pt:
    pt = replace_once(pt, "  'Loading': 'Carregando',\n};", "  'Loading': 'Carregando',\n" + extra_entries + "};", "ptBR extra entries")

old_translate = """function translate(value: string): string {
  let out = EXACT[value] ?? value;
  for (const [from, to] of Object.entries(EXACT).sort((a, b) => b[0].length - a[0].length)) {
    if (out.includes(from)) out = out.split(from).join(to);
  }
  for (const [pattern, replacement] of patterns) out = out.replace(pattern, replacement);
  return out;
}
"""
new_translate = """function translate(value: string): string {
  const match = value.match(/^(\\s*)(.*?)(\\s*)$/s);
  const prefix = match?.[1] ?? '';
  const core = match?.[2] ?? value;
  const suffix = match?.[3] ?? '';

  let out = EXACT[core] ?? core;
  if (out === core) {
    for (const [pattern, replacement] of patterns) out = out.replace(pattern, replacement);
  }
  return `${prefix}${out}${suffix}`;
}
"""
pt = replace_once(pt, old_translate, new_translate, "safe ptBR translate")
write(pt_path, pt)


# ---------------------------------------------------------------------------
# 6. Raridades e imagem fallback em português globalmente.
# ---------------------------------------------------------------------------
utils_path = "aninexus_frontend/src/utils/index.ts"
utils = read(utils_path)
old_rarity = """export function cleanRarityLabel(rarity: string) {
  return rarity
    .replace(
      /[\\u2700-\\u27bf]|[\\u2190-\\u21ff]|[\\u2000-\\u206f]|[\\u2600-\\u26ff]|[\\u2b00-\\u2bff]|[\\u00a0-\\u00bf]|\\u2013|\\u2014/g,
      '',
    )
    .trim();
}
"""
new_rarity = """const RARITY_PT: Record<string, string> = {
  common: 'Comum',
  medium: 'Médio',
  uncommon: 'Incomum',
  rare: 'Raro',
  legendary: 'Lendário',
  cosmic: 'Cósmico',
  immortal: 'Imortal',
  exclusive: 'Exclusivo',
  eternal: 'Eterno',
  royal: 'Real',
  mythical: 'Mítico',
  celestial: 'Celestial',
  divine: 'Divino',
  astral: 'Astral',
  prestige: 'Prestígio',
  starter: 'Inicial',
  epic: 'Épico',
};

export function cleanRarityLabel(rarity: string) {
  const cleaned = rarity
    .replace(
      /[\\u2700-\\u27bf]|[\\u2190-\\u21ff]|[\\u2000-\\u206f]|[\\u2600-\\u26ff]|[\\u2b00-\\u2bff]|[\\u00a0-\\u00bf]|\\u2013|\\u2014/g,
      '',
    )
    .trim();
  return RARITY_PT[cleaned.toLowerCase()] ?? cleaned;
}
"""
utils = replace_once(utils, old_rarity, new_rarity, "rarity localization")
utils = utils.replace("letter-spacing='2'>NO IMAGE</text>", "letter-spacing='2'>SEM IMAGEM</text>")
write(utils_path, utils)


# ---------------------------------------------------------------------------
# 7. Perfil: principais textos nativamente em português.
# ---------------------------------------------------------------------------
profile_path = "aninexus_frontend/src/pages/Profile.tsx"
profile = read(profile_path)
profile_replacements = {
    "const passLabel = `${passType.charAt(0).toUpperCase()}${passType.slice(1)} PASS`;": "const passLabel = passType === 'free' ? 'PASSE GRÁTIS' : passType === 'premium' ? 'PASSE PREMIUM' : 'PASSE ELITE';",
    ": 'UNRANKED';": ": 'SEM POSIÇÃO';",
    "user.titles?.current || 'OPERATOR'": "user.titles?.current || 'USUÁRIO'",
    "|| 'Operator'}": "|| 'Usuário'}",
    "label=\"EXPERIENCE\"": "label=\"EXPERIÊNCIA\"",
    ">\n                Archive\n              </span>": ">\n                Coleção\n              </span>",
    ">\n              Registry\n            </Badge>": ">\n              Registro\n            </Badge>",
    "                  COLLECTED": "                  COLECIONADOS",
    "label: 'Prisms'": "label: 'Dados'",
    "label: 'Rank'": "label: 'Posição'",
    "label: 'Streak'": "label: 'Sequência'",
    "} DAYS`": "} DIAS`",
    "              COMPANION": "              COMPANHEIRO",
    "activePet?.name || 'NONE ACTIVE'": "activePet?.name || 'NENHUM ATIVO'",
    "              INCUBATOR": "              INCUBADORA",
    "} ACTIVE": "} ATIVO",
    ">SYSTEM_OK</span>": ">SISTEMA OK</span>",
    "                  BONDED WITH": "                  VÍNCULO COM",
    ": 'BONDED';": ": 'VINCULADO';",
    "                  COMBAT RECORD": "                  HISTÓRICO DE DUELOS",
    "{formatNumber(battleStats.wins)}W / {formatNumber(battleStats.losses)}L": "{formatNumber(battleStats.wins)} V / {formatNumber(battleStats.losses)} D",
    "{Number(battleStats.win_rate || 0).toFixed(0)}% WR": "{Number(battleStats.win_rate || 0).toFixed(0)}% VITÓRIAS",
    "              Your collection": "              Sua coleção",
    "                Every waifu you've collected": "                Todos os personagens que você já coletou",
    "aria-label=\"Refresh collection\"": "aria-label=\"Atualizar coleção\"",
    "placeholder=\"Search characters...\"": "placeholder=\"Buscar personagens...\"",
    "aria-label=\"Filter by rarity\"": "aria-label=\"Filtrar por raridade\"",
    ">ALL RARITIES</option>": ">TODAS AS RARIDADES</option>",
    "title=\"Nothing here yet\"": "title=\"Nada por aqui ainda\"",
    "message=\"Hatch some eggs to start your collection.\"": "message=\"Use o Dado, jogos e ovos para aumentar sua coleção.\"",
}
for old, new in profile_replacements.items():
    if old in profile:
        profile = profile.replace(old, new)
write(profile_path, profile)


# ---------------------------------------------------------------------------
# 8. Incubadora: textos nativos em português.
# ---------------------------------------------------------------------------
hatch_path = "aninexus_frontend/src/pages/Hatchery.tsx"
hatch = read(hatch_path)
hatch_replacements = {
    "addToast('Incubation started.', 'success');": "addToast('Incubação iniciada.', 'success');",
    "result?.message || 'Egg sold.'": "result?.message || 'Ovo vendido.'",
    "result?.message || 'Egg purified.'": "result?.message || 'Ovo purificado.'",
    "result?.message || 'Eggs fused.'": "result?.message || 'Ovos fundidos.'",
    "{egg.remainingMins}m remaining": "{egg.remainingMins} min restantes",
    ">\n                    READY\n                  </Badge>": ">\n                    PRONTO\n                  </Badge>",
    "`${waitMin}m Cycle`": "`${waitMin} min de ciclo`",
    "'Standby'": "'Aguardando'",
    ">\n                    BOOSTED\n                  </Badge>": ">\n                    ACELERADO\n                  </Badge>",
    ">\n                    CORRUPTED\n                  </Badge>": ">\n                    CORROMPIDO\n                  </Badge>",
    "                  Start <ArrowRight": "                  Incubar <ArrowRight",
    "                    Purify <Droplets": "                    Purificar <Droplets",
    "                  Sell {egg.sell_price": "                  Vender {egg.sell_price",
    "                Hatch\n              </Button>": "                Chocar\n              </Button>",
    ">Hatchery</h1>": ">Incubadora</h1>",
    "label: 'Ready'": "label: 'Prontos'",
    "                  Fuse\n                </Button>": "                  Fundir\n                </Button>",
}
for old, new in hatch_replacements.items():
    if old in hatch:
        hatch = hatch.replace(old, new)
write(hatch_path, hatch)


# ---------------------------------------------------------------------------
# 9. Ranking: sem WebSocket inexistente; polling leve e textos corretos.
# ---------------------------------------------------------------------------
leader_path = "aninexus_frontend/src/pages/Leaderboard.tsx"
leader = read(leader_path)
start_marker = "  // Realtime updates: the backend publishes to a Redis channel whenever a\n"
end_marker = "  const METRICS = [\n"
start_i = leader.find(start_marker)
end_i = leader.find(end_marker, start_i)
if start_i < 0 or end_i < 0:
    raise RuntimeError("leaderboard realtime block não encontrado")
new_live_block = """  // Atualização automática sem depender de WebSocket no runtime atual.
  const fetchRef = useRef(fetchLeaderboard);
  fetchRef.current = fetchLeaderboard;

  useEffect(() => {
    const timer = window.setInterval(() => {
      void fetchRef.current();
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

"""
leader = leader[:start_i] + new_live_block + leader[end_i:]
leader = leader.replace("return `Operator ${String(user.id || index + 1)", "return `Usuário ${String(user.id || index + 1)")
leader = leader.replace(">Rankings</h1>", ">Ranking</h1>")
old_dot = """          <span
            className={cn(
              'w-1.5 h-1.5 rounded-full',
              live ? 'bg-emerald-500' : 'bg-zinc-700',
            )}
            title={live ? 'Live updates connected' : 'Live updates offline'}
          />
"""
new_dot = """          <span
            className="w-1.5 h-1.5 rounded-full bg-emerald-500"
            title="Atualização automática a cada 30 segundos"
          />
"""
leader = replace_once(leader, old_dot, new_dot, "leaderboard live indicator")
leader = leader.replace("{data.length - visible} hidden", "{data.length - visible} ocultos")
write(leader_path, leader)


# ---------------------------------------------------------------------------
# 10. Trocas: garantir proporção real dos cards e sequência dos passos.
# ---------------------------------------------------------------------------
trade_path = "aninexus_frontend/src/pages/Trading.tsx"
trade = read(trade_path)
trade = replace_once(
    trade,
    """      className={cn(
        'relative rounded-md overflow-hidden aspect-[2/3] border transition-all text-left',
""",
    """      style={{ aspectRatio: '2 / 3' }}
      className={cn(
        'relative w-full min-w-0 rounded-md overflow-hidden border transition-all text-left',
""",
    "trade card aspect ratio",
)
trade = trade.replace(
    "            {(myLoading || myChars.length > 0) && (",
    "            {targetChars.length > 0 && (myLoading || myChars.length > 0) && (",
)
trade = trade.replace("className=\"aspect-[2/3] rounded-md\"", "className=\"h-36 rounded-md\"")
write(trade_path, trade)


print("AniNexus live polish patch applied")
