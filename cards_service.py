 import json
 import os
 import re
 import tempfile
 import unicodedata
 from copy import deepcopy
 from threading import RLock
 from typing import Any, Dict, List, Optional
 
 BASE_DIR = os.path.dirname(os.path.abspath(__file__))
 DATA_DIR = os.path.join(BASE_DIR, "data")
 
 CARDS_ASSETS_PATH = os.getenv(
     "CARDS_ASSETS_PATH",
     os.path.join(DATA_DIR, "personagens_anilist.txt"),
 ).strip()
 
 CARDS_OVERRIDES_PATH = os.getenv(
     "CARDS_OVERRIDES_PATH",
     os.path.join(DATA_DIR, "cards_overrides.json"),
 ).strip()
 
 _LOCK = RLock()
 _CACHE: Optional[Dict[str, Any]] = None
 
 
 def _default_overrides() -> Dict[str, Any]:
     return {
@@ -57,122 +58,149 @@ def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
         suffix=".tmp",
         dir=os.path.dirname(path),
     )
 
     try:
         with os.fdopen(fd, "w", encoding="utf-8") as f:
             json.dump(data, f, ensure_ascii=False, indent=2)
 
         os.replace(tmp_path, path)
 
     finally:
         if os.path.exists(tmp_path):
             try:
                 os.remove(tmp_path)
             except Exception:
                 pass
 
 
 def load_cards_assets_raw() -> List[Dict[str, Any]]:
     if not os.path.exists(CARDS_ASSETS_PATH):
         raise FileNotFoundError(
             f"Arquivo de assets não encontrado: {CARDS_ASSETS_PATH}"
         )
 
     with open(CARDS_ASSETS_PATH, "r", encoding="utf-8") as f:
         raw = json.load(f)
         content = f.read()
 
     try:
         raw = json.loads(content)
     except json.JSONDecodeError:
         repaired = _repair_common_missing_commas(content)
         raw = json.loads(repaired)
 
     if isinstance(raw, dict):
-        items = raw.get("items", [])
+        items = raw.get("items") or raw.get("Unid") or raw.get("animes") or []
     elif isinstance(raw, list):
         items = raw
     else:
         items = []
 
     cleaned: List[Dict[str, Any]] = []
 
     for anime in items:
         if not isinstance(anime, dict):
             continue
 
         try:
             anime_id = int(anime.get("anime_id"))
         except Exception:
             continue
 
         anime_name = str(anime.get("anime") or "").strip()
         if not anime_name:
             continue
 
         banner_image = str(anime.get("banner_image") or "").strip()
-        cover_image = str(anime.get("cover_image") or "").strip()
+        cover_image = str(anime.get("cover_image") or anime.get("imagem_de_capa") or "").strip()
 
         chars_clean: List[Dict[str, Any]] = []
         seen_ids = set()
 
-        for ch in anime.get("characters", []) or []:
+        for ch in (anime.get("characters") or anime.get("personagens") or []):
             if not isinstance(ch, dict):
                 continue
 
             try:
                 cid = int(ch.get("id"))
             except Exception:
                 continue
 
             if cid in seen_ids:
                 continue
 
-            name = str(ch.get("name") or "").strip()
-            image = str(ch.get("image") or "").strip()
+            name = str(ch.get("name") or ch.get("nome") or "").strip()
+            image = str(ch.get("image") or ch.get("imagem") or "").strip()
 
             if not name:
                 continue
 
             seen_ids.add(cid)
 
             chars_clean.append({
                 "id": cid,
                 "name": name,
                 "image": image,
                 "anime_id": anime_id,
                 "anime": anime_name,
             })
 
         chars_clean.sort(key=lambda x: _normalize_text(x["name"]))
 
         cleaned.append({
             "anime_id": anime_id,
             "anime": anime_name,
             "banner_image": banner_image,
             "cover_image": cover_image,
             "characters": chars_clean,
         })
 
     cleaned.sort(key=lambda x: _normalize_text(x["anime"]))
     return cleaned
 
 
+def _repair_common_missing_commas(content: str) -> str:
+    lines = content.splitlines()
+    repaired: List[str] = []
+
+    for idx, line in enumerate(lines):
+        stripped = line.rstrip()
+        next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
+        next_lstripped = next_line.lstrip()
+
+        is_property_line = bool(re.match(r'^\s*"[^"\\]+"\s*:\s*.+$', stripped))
+        needs_comma = (
+            is_property_line
+            and not stripped.endswith((",", "{", "["))
+            and next_lstripped.startswith('"')
+        )
+
+        repaired.append(stripped + "," if needs_comma else line)
+
+    return "\n".join(repaired)
+
+
 def load_cards_overrides() -> Dict[str, Any]:
     _ensure_data_dir()
 
     if not os.path.exists(CARDS_OVERRIDES_PATH):
         data = _default_overrides()
         _atomic_write_json(CARDS_OVERRIDES_PATH, data)
         return data
 
     try:
         with open(CARDS_OVERRIDES_PATH, "r", encoding="utf-8") as f:
             raw = json.load(f)
     except Exception:
         raw = {}
 
     data = _default_overrides()
     if isinstance(raw, dict):
         data.update(raw)
 
     for key in ["deleted_characters", "deleted_animes", "custom_animes", "custom_characters"]:
         if not isinstance(data.get(key), list):
             data[key] = []
 
     for key in [
         "character_image_overrides",
         "character_name_overrides",
