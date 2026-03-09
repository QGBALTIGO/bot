 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/commands/card.py b/commands/card.py
index b78af94556a02573c4c409ec0d653987afe07bd5..fc12acf7e0e2b0f442a93addb5b134b09783c3df 100644
--- a/commands/card.py
+++ b/commands/card.py
@@ -1,116 +1,80 @@
-import json
 import os
 import re
 from typing import Dict, Any, Optional
 
 from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
 from telegram.ext import ContextTypes
 
 from utils.runtime_guard import lock_manager, rate_limiter
 
 from database import (
     get_user_card_quantity,
     get_card_owner_count,
     get_card_total_copies,
 )
 
-BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
-
-DATA_PATHS = [
-    os.path.join(BASE_DIR, "data", "personagens_anilist.txt"),
-    os.path.join(BASE_DIR, "dados", "personagens_anilist.txt"),
-]
+from cards_service import build_cards_final_data
 
 _chars_cache: Optional[Dict[int, Dict[str, Any]]] = None
 
 
 CARD_CALLBACK_RATE_LIMIT = int(os.getenv("CARD_CALLBACK_RATE_LIMIT", "4"))
 CARD_CALLBACK_RATE_WINDOW_SECONDS = float(os.getenv("CARD_CALLBACK_RATE_WINDOW_SECONDS", "3"))
 
 
 
 def get_dup_emoji(qty: int) -> str:
     if qty >= 20:
         return " 👑"
     elif qty >= 15:
         return " 🌟"
     elif qty >= 10:
         return " ⭐"
     elif qty >= 5:
         return " 💫"
     elif qty >= 2:
         return " ✨"
     return ""
 
 
-def _resolve_path():
-    for p in DATA_PATHS:
-        if os.path.exists(p):
-            return p
-    raise FileNotFoundError("personagens_anilist.txt não encontrado")
-
-
 def load_characters():
     global _chars_cache
 
     if _chars_cache is not None:
         return _chars_cache
 
-    path = _resolve_path()
-
-    with open(path, "r", encoding="utf-8") as f:
-        raw = json.load(f)
-
-    if isinstance(raw, dict):
-        items = raw.get("items", [])
-    else:
-        items = raw
-
-    chars = {}
-
-    for anime in items:
-        if not isinstance(anime, dict):
-            continue
-
-        anime_name = anime.get("anime") or "Obra desconhecida"
-
-        for c in anime.get("characters", []):
-            if not isinstance(c, dict):
-                continue
-
-            try:
-                cid = int(c["id"])
-            except Exception:
-                continue
-
-            chars[cid] = {
-                "id": cid,
-                "name": c.get("name", "Sem nome"),
-                "image": c.get("image"),
-                "anime": anime_name,
-            }
+    data = build_cards_final_data()
+    chars = {
+        int(cid): {
+            "id": int(ch["id"]),
+            "name": ch.get("name", "Sem nome"),
+            "image": ch.get("image"),
+            "anime": ch.get("anime", "Obra desconhecida"),
+        }
+        for cid, ch in data["characters_by_id"].items()
+    }
 
     _chars_cache = chars
     return chars
 
 
 def find_character_by_name(name: str):
     name = name.lower().strip()
 
     chars = load_characters()
 
     for c in chars.values():
         if c["name"].lower() == name:
             return c
 
     for c in chars.values():
         if c["name"].lower().startswith(name):
             return c
 
     for c in chars.values():
         if name in c["name"].lower():
             return c
 
     return None
 
 
 
EOF
)
