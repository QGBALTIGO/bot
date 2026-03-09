 import hashlib
 import json
 import os
 import tempfile
 import unicodedata
 from copy import deepcopy
 from threading import RLock
 from typing import Any, Dict, List, Optional
 
+from database import list_all_card_character_catalog
+
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
 
 
+def _load_assets_from_db() -> List[Dict[str, Any]]:
+    rows = list_all_card_character_catalog()
+    animes_map: Dict[str, Dict[str, Any]] = {}
+
+    for row in rows:
+        try:
+            cid = int(row.get("character_id"))
+        except Exception:
+            continue
+
+        anime_name = str(row.get("anime_name") or "").strip()
+        char_name = str(row.get("character_name") or "").strip()
+        if not anime_name or not char_name:
+            continue
+
+        image = str(row.get("image_url") or "").strip()
+        anime_key = _normalize_text(anime_name)
+
+        anime_obj = animes_map.get(anime_key)
+        if not anime_obj:
+            anime_obj = {
+                "anime_id": int(hashlib.md5(anime_key.encode("utf-8")).hexdigest()[:8], 16),
+                "anime": anime_name,
+                "banner_image": "",
+                "cover_image": "",
+                "characters": [],
+            }
+            animes_map[anime_key] = anime_obj
+
+        anime_obj["characters"].append({
+            "id": cid,
+            "name": char_name,
+            "image": image,
+            "anime_id": anime_obj["anime_id"],
+            "anime": anime_name,
+        })
+
+    cleaned = list(animes_map.values())
+    for anime in cleaned:
+        seen_ids = set()
+        deduped = []
+        for ch in anime["characters"]:
+            cid = int(ch["id"])
+            if cid in seen_ids:
+                continue
+            seen_ids.add(cid)
+            deduped.append(ch)
+        deduped.sort(key=lambda x: _normalize_text(x["name"]))
+        anime["characters"] = deduped
+
+    cleaned.sort(key=lambda x: _normalize_text(x["anime"]))
+    return cleaned
+
+
 def _default_overrides() -> Dict[str, Any]:
     return {
         "deleted_characters": [],
         "deleted_animes": [],
         "custom_animes": [],
         "custom_characters": [],
         "character_image_overrides": {},
         "character_name_overrides": {},
         "anime_name_overrides": {},
         "anime_banner_overrides": {},
         "anime_cover_overrides": {},
         "subcategories": {},
     }
 
 
 def _ensure_data_dir() -> None:
     os.makedirs(os.path.dirname(CARDS_OVERRIDES_PATH), exist_ok=True)
 
 
 def _normalize_text(text: Any) -> str:
     text = str(text or "").strip().lower()
     text = unicodedata.normalize("NFKD", text)
     text = "".join(ch for ch in text if not unicodedata.combining(ch))
     return " ".join(text.split())
 
@@ -52,56 +109,57 @@ def _normalize_text(text: Any) -> str:
 def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
     os.makedirs(os.path.dirname(path), exist_ok=True)
 
     fd, tmp_path = tempfile.mkstemp(
         prefix="cards_",
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
-        raise FileNotFoundError(
-            f"Arquivo de assets não encontrado: {CARDS_ASSETS_PATH}"
-        )
+        return _load_assets_from_db()
 
-    with open(CARDS_ASSETS_PATH, "r", encoding="utf-8") as f:
-        raw = json.load(f)
+    try:
+        with open(CARDS_ASSETS_PATH, "r", encoding="utf-8") as f:
+            raw = json.load(f)
+    except Exception:
+        return _load_assets_from_db()
 
     if isinstance(raw, dict):
         items = raw.get("items", [])
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
         cover_image = str(anime.get("cover_image") or "").strip()
