from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1, encontrado {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Backend entrypoint: router real de vínculos/duelos antes da compatibilidade.
# ---------------------------------------------------------------------------
entry_path = "webapp_entrypoint.py"
entry = read(entry_path)
entry = replace_once(
    entry,
    "from webapp_routes.aninexus_admin_media import build_aninexus_admin_media_router\n",
    "from webapp_routes.aninexus_admin_media import build_aninexus_admin_media_router\nfrom webapp_routes.aninexus_bonds_duels import build_aninexus_bonds_duels_router\n",
    "entry import bonds duels",
)
entry = replace_once(
    entry,
    "aninexus_admin_media_router = build_aninexus_admin_media_router()\n",
    "aninexus_admin_media_router = build_aninexus_admin_media_router()\naninexus_bonds_duels_router = build_aninexus_bonds_duels_router()\n",
    "entry instantiate bonds duels",
)
anchor = """    if not aninexus_social_paths.issubset(registered_paths):
        app.include_router(aninexus_social_router)
        registered_paths.update(aninexus_social_paths)

"""
bond_block = """    aninexus_bonds_duels_paths = {
        "/api/v1_7b82/social/marriage",
        "/api/v1_7b82/social/bond",
        "/api/v1_7b82/social/bond/invites",
        "/api/v1_7b82/social/bond/invite",
        "/api/v1_7b82/social/bond/invites/{invite_id}/respond",
        "/api/v1_7b82/duels/history",
    }
    if not aninexus_bonds_duels_paths.issubset(registered_paths):
        app.include_router(aninexus_bonds_duels_router)
        registered_paths.update(aninexus_bonds_duels_paths)

"""
entry = replace_once(entry, anchor, anchor + bond_block, "entry register bonds duels")
entry = replace_once(
    entry,
    "        \"/api/v1_7b82/social/marriage\",\n",
    "",
    "remove marriage compat path",
)
write(entry_path, entry)


# ---------------------------------------------------------------------------
# Remover o endpoint social/marriage falso da camada de compatibilidade.
# ---------------------------------------------------------------------------
compat_path = "webapp_routes/aninexus_compat.py"
compat = read(compat_path)
marriage_block = """    @router.get("/social/marriage")
    def marriage(authorization: str = Header(default="")):
        try:
            _require_user(authorization)
        except PermissionError as exc:
            return _unauthorized(str(exc))
        return JSONResponse(None)


"""
compat = replace_once(compat, marriage_block, "", "remove fake marriage route")
write(compat_path, compat)


# ---------------------------------------------------------------------------
# App: novas abas Duelos e Vínculos.
# ---------------------------------------------------------------------------
app_path = "aninexus_frontend/src/App.tsx"
app = read(app_path)
app = replace_once(
    app,
    "const Dado = lazy(() => import('./pages/Dado').then((m) => ({ default: m.Dado })));\n",
    "const Dado = lazy(() => import('./pages/Dado').then((m) => ({ default: m.Dado })));\nconst Duels = lazy(() => import('./pages/Duels').then((m) => ({ default: m.Duels })));\nconst Bonds = lazy(() => import('./pages/Bonds').then((m) => ({ default: m.Bonds })));\n",
    "app lazy social pages",
)
app = replace_once(
    app,
    "  'trading',\n];",
    "  'trading',\n  'duels',\n  'bonds',\n];",
    "app valid social tabs",
)
app = replace_once(
    app,
    "  swap: 'trading',\n};",
    "  swap: 'trading',\n  duel: 'duels',\n  duels: 'duels',\n  battle: 'duels',\n  combat: 'duels',\n  bond: 'bonds',\n  bonds: 'bonds',\n  relationship: 'bonds',\n  relationships: 'bonds',\n  marriage: 'bonds',\n  vinculo: 'bonds',\n  vinculos: 'bonds',\n};",
    "app social aliases",
)
app = replace_once(
    app,
    "            {activeTab === 'trading' && <Trading />}\n",
    "            {activeTab === 'trading' && <Trading />}\n            {activeTab === 'duels' && <Duels />}\n            {activeTab === 'bonds' && <Bonds />}\n",
    "app social renders",
)
write(app_path, app)


# ---------------------------------------------------------------------------
# Drawer: Duelos e Vínculos como funções sociais reais.
# ---------------------------------------------------------------------------
drawer_path = "aninexus_frontend/src/components/NavigationDrawer.tsx"
drawer = read(drawer_path)
if "  Swords,\n" not in drawer:
    drawer = replace_once(drawer, "  Store,\n", "  Store,\n  Swords,\n", "drawer swords import")
drawer = replace_once(
    drawer,
    "    items: [\n      { id: 'trading', label: 'Trocas', icon: ArrowLeftRight },\n",
    "    items: [\n      { id: 'duels', label: 'Duelos', icon: Swords },\n      { id: 'bonds', label: 'Vínculos', icon: Heart },\n      { id: 'trading', label: 'Trocas', icon: ArrowLeftRight },\n",
    "drawer social entries",
)
write(drawer_path, drawer)


# ---------------------------------------------------------------------------
# Conquistas: texto nativo pt-BR.
# ---------------------------------------------------------------------------
ach_path = "aninexus_frontend/src/pages/Achievements.tsx"
ach = read(ach_path)
for old, new in {
    ">Milestones</h1>": ">Conquistas</h1>",
    "Bragging rights you've earned": "Marcos que você conquistou",
    "                Progress\n": "                Progresso\n",
    "                Rank\n": "                Classificação\n",
    "                  Collector\n": "                  Colecionador\n",
    "                  Keep hatching\n": "                  Continue evoluindo\n",
    "                        CLEAR\n": "                        CONCLUÍDA\n",
}.items():
    if old in ach:
        ach = ach.replace(old, new)
write(ach_path, ach)


# ---------------------------------------------------------------------------
# Missões: remover últimos textos ingleses visíveis.
# ---------------------------------------------------------------------------
quests_path = "aninexus_frontend/src/pages/Quests.tsx"
quests = read(quests_path)
for old, new in {
    'label="Progress"': 'label="Progresso"',
    "{isComplete ? 'Claim' : <Lock size={14} />}": "{isComplete ? 'Resgatar' : <Lock size={14} />}",
    "addToast(`Mission complete: +${res.reward_shards} Coins`, 'success');": "addToast(`Missão concluída: +${res.reward_shards} Coins`, 'success');",
    "            No Missions Available": "            Nenhuma missão disponível",
    ">Missions</h1>": ">Missões</h1>",
    "          Operational objectives & bounties": "          Objetivos diários e semanais do AniNexus",
    "{renderQuestSection('DAILY OPERATIONS'": "{renderQuestSection('MISSÕES DIÁRIAS'",
    "{renderQuestSection('STRATEGIC WEEKLY'": "{renderQuestSection('MISSÕES SEMANAIS'",
    "{renderQuestSection('PASS CLEARANCE'": "{renderQuestSection('TEMPORADA'",
}.items():
    if old in quests:
        quests = quests.replace(old, new)
write(quests_path, quests)


# ---------------------------------------------------------------------------
# Meus Companheiros: texto nativo pt-BR.
# ---------------------------------------------------------------------------
my_pets_path = "aninexus_frontend/src/pages/MyPets.tsx"
my_pets = read(my_pets_path)
for old, new in {
    "              ACTIVE\n": "              ATIVO\n",
    "{pet.desc || pet.ability || 'Loyal companion'}": "{pet.desc || pet.ability || 'Companheiro leal'}",
    'label="Vitality"': 'label="Vitalidade"',
    'label="Strike"': 'label="Ataque"',
    'label="Velocity"': 'label="Velocidade"',
    'label="Luck"': 'label="Sorte"',
    "            SYNC: {pet.affection ?? 0}%": "            VÍNCULO: {pet.affection ?? 0}%",
    'label="XP to next level"': 'label="XP para o próximo nível"',
    "<Beef size={13} className=\"mr-1.5\" /> Feed": "<Beef size={13} className=\"mr-1.5\" /> Alimentar",
    "<Dumbbell size={13} className=\"mr-1.5\" /> Train": "<Dumbbell size={13} className=\"mr-1.5\" /> Treinar",
    "addToast(result?.message || 'Done.', 'success');": "addToast(result?.message || 'Concluído.', 'success');",
    "addToast(`${pet.name} activated.`, 'success');": "addToast(`${pet.name} foi ativado.`, 'success');",
    "                Companions\n": "                Companheiros\n",
    "              Your pets, their levels and bonds": "              Seus companheiros, níveis e vínculos",
    "              Active pet\n": "              Companheiro ativo\n",
    "              All pets\n": "              Todos os companheiros\n",
    "              Sorted by level\n": "              Ordenados por nível\n",
    "{pet.ability || 'No special ability'}": "{pet.ability || 'Sem habilidade especial'}",
    "                              Bond {pet.affection ?? 0}%": "                              Vínculo {pet.affection ?? 0}%",
    "{isActive ? 'Active Companion' : 'Activate'}": "{isActive ? 'Companheiro ativo' : 'Ativar'}",
    "                  No pets yet — visit the Breeder": "                  Nenhum companheiro ainda — visite a Loja de Companheiros",
}.items():
    if old in my_pets:
        my_pets = my_pets.replace(old, new)
write(my_pets_path, my_pets)


# ---------------------------------------------------------------------------
# Modal de companheiro: traduzir o que ainda aparece ao abrir um pet.
# ---------------------------------------------------------------------------
pet_modal_path = "aninexus_frontend/src/components/pet/PetActionModal.tsx"
pet_modal = read(pet_modal_path)
for old, new in {
    "addToast(`${selectedPet.name} activated.`, 'success');": "addToast(`${selectedPet.name} foi ativado.`, 'success');",
    "                  No Image\n": "                  Sem imagem\n",
    "                  PET ID: ": "                  ID DO COMPANHEIRO: ",
    "{selectedPet.ability || 'SYSTEM_SUPPORT_PERK'}": "{selectedPet.ability || 'SEM HABILIDADE ESPECIAL'}",
    "label: 'Vitality'": "label: 'Vitalidade'",
    "label: 'Strike'": "label: 'Ataque'",
    "label: 'Velocity'": "label: 'Velocidade'",
    "label: 'Luck'": "label: 'Sorte'",
    "                      Progress\n": "                      Progresso\n",
    "                      History\n": "                      Histórico\n",
    "                      Set Active\n": "                      Tornar ativo\n",
    "                      Active Companion\n": "                      Companheiro ativo\n",
}.items():
    if old in pet_modal:
        pet_modal = pet_modal.replace(old, new)
write(pet_modal_path, pet_modal)


print("AniNexus duel/social patch applied")
