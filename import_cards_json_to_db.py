 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/import_cards_json_to_db.py b/import_cards_json_to_db.py
index 50e6529995c05c0bd95479ed93e4e49ac8b676a8..2aaab7603947e1389df7b51328f18638e3922398 100644
--- a/import_cards_json_to_db.py
+++ b/import_cards_json_to_db.py
@@ -25,50 +25,78 @@ def resolve_path():
 
 def load_json_file(path: str):
     with open(path, "r", encoding="utf-8") as f:
         raw = json.load(f)
 
     if isinstance(raw, dict):
         items = raw.get("items", raw.get("characters", []))
     elif isinstance(raw, list):
         items = raw
     else:
         items = []
 
     if not isinstance(items, list):
         raise ValueError("Formato inválido: esperado lista de personagens.")
 
     return items
 
 
 def normalize_items(items):
     normalized = []
 
     for item in items:
         if not isinstance(item, dict):
             continue
 
+        # formato agrupado por anime: {anime, characters:[...]}
+        if isinstance(item.get("characters"), list):
+            anime = str(item.get("anime") or "").strip()
+            if not anime:
+                continue
+
+            for ch in item.get("characters", []):
+                if not isinstance(ch, dict):
+                    continue
+                try:
+                    char_id = int(ch.get("id"))
+                except Exception:
+                    continue
+
+                name = str(ch.get("name") or "").strip()
+                image = str(ch.get("image") or "").strip()
+                if not name:
+                    continue
+
+                normalized.append({
+                    "id": char_id,
+                    "name": name,
+                    "anime": anime,
+                    "image": image,
+                })
+            continue
+
+        # formato flat: {id, name, anime, image}
         try:
             char_id = int(item.get("id"))
         except Exception:
             continue
 
         name = str(item.get("name") or "").strip()
         anime = str(item.get("anime") or "").strip()
         image = str(item.get("image") or "").strip()
 
         if not name or not anime:
             continue
 
         normalized.append({
             "id": char_id,
             "name": name,
             "anime": anime,
             "image": image,
         })
 
     return normalized
 
 
 def main():
     path = resolve_path()
     items = load_json_file(path)
 
EOF
)
