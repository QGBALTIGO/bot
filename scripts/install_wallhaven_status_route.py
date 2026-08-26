from pathlib import Path

path = Path('webapp.py')
text = path.read_text(encoding='utf-8')
marker = 'from utils.wallhaven_curator_status import router as wallhaven_curator_status_router'
if marker not in text:
    text = text.rstrip() + '\n\n# System diagnostics: aggregate Wallhaven curator status.\n' + marker + '\napp.include_router(wallhaven_curator_status_router)\n'
path.write_text(text, encoding='utf-8')
