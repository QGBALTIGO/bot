from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: esperado 1, encontrado {count}")
    return text.replace(old, new, 1)


entry = Path("webapp_entrypoint.py")
entry_text = entry.read_text(encoding="utf-8")
entry_text = replace_once(
    entry_text,
    "from webapp_services.collection import collection_cards_from_snapshot, collection_snapshot\n",
    "from webapp_services.collection import (\n    collection_cards_from_snapshot,\n    collection_snapshot,\n)\n",
    "collection import",
)
entry.write_text(entry_text, encoding="utf-8")

compat = Path("webapp_routes/aninexus_compat.py")
compat_text = compat.read_text(encoding="utf-8")
start = compat_text.find('    @router.get("/achievements/list")')
end = compat_text.find('    @router.get("/admin/rarities")', start)
if start < 0 or end < 0:
    raise RuntimeError("bloco de fallbacks substituídos não encontrado")
compat_text = compat_text[:start] + compat_text[end:]
compat.write_text(compat_text, encoding="utf-8")

print("AniNexus CI cleanup applied")
