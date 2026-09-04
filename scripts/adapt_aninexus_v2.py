from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RENAMES = [
    ("seal_frontend", "aninexus_frontend"),
    ("seal_runtime", "aninexus_runtime"),
    ("seal_progression.py", "aninexus_progression.py"),
    ("database_seal_progression.py", "database_aninexus_progression.py"),
    ("webapp_routes/seal_compat.py", "webapp_routes/aninexus_compat.py"),
    ("webapp_routes/seal_progression.py", "webapp_routes/aninexus_progression.py"),
    ("webapp_routes/seal_runtime.py", "webapp_routes/aninexus_runtime.py"),
    ("tests/test_seal_compat.py", "tests/test_aninexus_compat.py"),
]

for source, target in RENAMES:
    src = ROOT / source
    dst = ROOT / target
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)

REPLACEMENTS = [
    ("database_seal_progression", "database_aninexus_progression"),
    ("seal_frontend", "aninexus_frontend"),
    ("seal_runtime", "aninexus_runtime"),
    ("seal_progression", "aninexus_progression"),
    ("seal_compat", "aninexus_compat"),
    ("build_seal_compat_router", "build_aninexus_compat_router"),
    ("build_seal_progression_router", "build_aninexus_progression_router"),
    ("install_seal_runtime", "install_aninexus_runtime"),
    ("SEAL_SESSION_TTL_SECONDS", "ANINEXUS_SESSION_TTL_SECONDS"),
    ("SEAL_SESSION_SECRET", "ANINEXUS_SESSION_SECRET"),
    ("seal-source-session", "aninexus-source-session"),
    ("seal_intro_seen", "aninexus_intro_seen"),
    ("seal-token.", "aninexus-token."),
    ("SealYourWaifuBot", "SourceBaltigo_Bot"),
    ("SEAL YOUR WAIFU", "ANINEXUS"),
    ("Seal Your Waifu", "AniNexus"),
    ("SEAL", "ANINEXUS"),
]

TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".html", ".md", ".toml", ".yml", ".yaml"}
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        continue
    if ".git" in path.parts or "node_modules" in path.parts:
        continue
    if path.name == "LICENSE":
        continue
    text = path.read_text(encoding="utf-8")
    new = text
    for old, replacement in REPLACEMENTS:
        new = new.replace(old, replacement)
    if new != text:
        path.write_text(new, encoding="utf-8")

frontend = ROOT / "aninexus_frontend"

# HTML base.
index_path = frontend / "index.html"
index = index_path.read_text(encoding="utf-8")
index = index.replace('<html lang="en">', '<html lang="pt-BR">')
index = re.sub(r"<title>.*?</title>", "<title>AniNexus</title>", index, count=1)
index_path.write_text(index, encoding="utf-8")

# App: Dado como módulo próprio, sem misturar com os dois minigames.
app_path = frontend / "src/App.tsx"
app = app_path.read_text(encoding="utf-8")
if "const Dado = lazy(" not in app:
    anchor = "const Trading = lazy(() => import('./pages/Trading').then((m) => ({ default: m.Trading })));"
    app = app.replace(anchor, anchor + "\nconst Dado = lazy(() => import('./pages/Dado').then((m) => ({ default: m.Dado })));", 1)
if "  'dado'," not in app:
    app = app.replace("  'profile',\n  'incubation',", "  'profile',\n  'dado',\n  'incubation',", 1)
if "  dado: 'dado'," not in app:
    app = app.replace("  profile: 'profile',", "  profile: 'profile',\n  dado: 'dado',\n  dice: 'dado',\n  roll: 'dado',", 1)
if "{activeTab === 'dado' && <Dado />}" not in app:
    app = app.replace("            {activeTab === 'incubation' && <Hatchery />}", "            {activeTab === 'dado' && <Dado />}\n            {activeTab === 'incubation' && <Hatchery />}", 1)
app_path.write_text(app, encoding="utf-8")

# Drawer: navegação AniNexus em português + Dado.
drawer_path = frontend / "src/components/NavigationDrawer.tsx"
drawer = drawer_path.read_text(encoding="utf-8")
if "  Dices," not in drawer:
    drawer = drawer.replace("  ChartNoAxesColumnIncreasing,", "  ChartNoAxesColumnIncreasing,\n  Dices,", 1)
if "{ id: 'dado', label: 'Dado', icon: Dices }," not in drawer:
    drawer = drawer.replace(
        "      { id: 'profile', label: 'Dashboard', icon: LayoutDashboard },",
        "      { id: 'profile', label: 'Painel', icon: LayoutDashboard },\n      { id: 'dado', label: 'Dado', icon: Dices },",
        1,
    )
for old, new in {
    "title: 'CORE'": "title: 'PRINCIPAL'",
    "title: 'OPERATIONS'": "title: 'RECURSOS'",
    "title: 'COMMAND'": "title: 'ADMINISTRAÇÃO'",
    "label: 'Dashboard'": "label: 'Painel'",
    "label: 'Hatchery'": "label: 'Incubadora'",
    "label: 'Market'": "label: 'Loja'",
    "label: 'Currency'": "label: 'Economia'",
    "label: 'Archive'": "label: 'Coleção'",
    "label: 'Companions'": "label: 'Companheiros'",
    "label: 'Nexus Games'": "label: 'Jogos AniNexus'",
    "label: 'Milestones'": "label: 'Conquistas'",
    "label: 'Trading'": "label: 'Trocas'",
    "label: 'Recruit'": "label: 'Indicações'",
    "label: 'Tasks'": "label: 'Missões'",
    "label: 'Season Pass'": "label: 'Temporada'",
    "label: 'Rankings'": "label: 'Ranking'",
    "label: 'Registry Feed'": "label: 'Cadastro'",
    "label: 'Crew Manifest'": "label: 'Equipe'",
    "ACCOUNT": "CONTA",
    ">Logout<": ">Sair<",
    ">Confirm<": ">Confirmar<",
    ">Cancel<": ">Cancelar<",
    "Server status": "Status do servidor",
    "Signed in": "Conectado",
}.items():
    drawer = drawer.replace(old, new)
drawer_path.write_text(drawer, encoding="utf-8")

# Header: AniNexus + Dados no lugar da moeda paralela antiga.
header_path = frontend / "src/components/Header.tsx"
header = header_path.read_text(encoding="utf-8")
header = header.replace("Coins, Gem, Menu", "Coins, Dices, Menu")
header = header.replace("<Gem size={12}", "<Dices size={12}")
header = header.replace("PRISMS", "DADOS")
header = header.replace("Go to Dashboard", "Ir para o painel")
header = header.replace("Open Menu", "Abrir menu")
header = header.replace("User avatar", "Avatar do usuário")
header_path.write_text(header, encoding="utf-8")

# Ranking: usa as cinco métricas que já existem no Source.
leader_path = frontend / "src/pages/Leaderboard.tsx"
leader = leader_path.read_text(encoding="utf-8")
leader = leader.replace("  Gem,\n", "")
leader = leader.replace("const [metric, setMetric] = useState('harem');", "const [metric, setMetric] = useState('collection');")
leader = re.sub(
    r"  const METRICS = \[.*?\n  \];",
    """  const METRICS = [
    { id: 'collection', label: 'Coleção', icon: BookOpen },
    { id: 'coins', label: 'Coins', icon: Coins },
    { id: 'level', label: 'Nível', icon: TrendingUp },
    { id: 'termo', label: 'Termo', icon: Brain },
    { id: 'memory', label: 'Memória', icon: ChartNoAxesColumnIncreasing },
  ];""",
    leader,
    count=1,
    flags=re.S,
)
leader = leader.replace("Top collectors across the game", "Melhores jogadores do AniNexus")
leader = leader.replace("No ranking data", "Sem dados de ranking")
leader = leader.replace("Load more", "Carregar mais")
leader_path.write_text(leader, encoding="utf-8")

# Bot info/compatibilidade e mensagens de sessão.
compat_path = ROOT / "webapp_routes/aninexus_compat.py"
compat = compat_path.read_text(encoding="utf-8")
compat = compat.replace('"Session expired. Please reopen the app."', '"Sessão expirada. Reabra a MiniApp."')
compat = compat.replace('"This system is not connected to Source yet."', '"Este recurso ainda está em integração com o Source."')
compat = compat.replace('        return JSONResponse({})\n\n    @router.get("/harem")', '        return JSONResponse({"name": "AniNexus"})\n\n    @router.get("/harem")', 1)
compat = compat.replace("Player collection lookup is not connected yet.", "A consulta de coleção de outro usuário ainda não está disponível.")
compat_path.write_text(compat, encoding="utf-8")

# Runtime: mantém /menu e adiciona /aninexus como preview explícito.
runtime_path = ROOT / "webapp_routes/aninexus_runtime.py"
runtime = runtime_path.read_text(encoding="utf-8")
runtime = runtime.replace('if "/seal" not in existing_paths:', 'if "/aninexus" not in existing_paths:')
runtime = runtime.replace('"/seal",', '"/aninexus",')
runtime_path.write_text(runtime, encoding="utf-8")

# README do frontend deixa explícita a adaptação e a atribuição da licença.
readme = frontend / "README.md"
readme.write_text(
    "# AniNexus MiniApp\n\n"
    "Frontend da MiniApp AniNexus, adaptado para o ecossistema Source Baltigo.\n\n"
    "A base visual e componentes derivam do projeto Seal Your Waifu, de bisug, "
    "mantendo a atribuição exigida pela licença original em `LICENSE`.\n",
    encoding="utf-8",
)

print("Adaptação AniNexus aplicada.")
