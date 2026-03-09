 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/database.py b/database.py
index 2587a7668cbbbf807c60d36d3e25085f6a27e55c..1a759cc280683dec36d8f46a223da1bd31b88c09 100644
--- a/database.py
+++ b/database.py
@@ -798,25 +798,42 @@ def admin_set_card_character_anime(character_id: int, anime_name: str):
     WHERE character_id = %s;
     """, (str(anime_name).strip(), int(character_id)))
 
 
 def admin_delete_card_character(character_id: int):
     _run("""
     UPDATE card_characters_catalog
     SET is_deleted = TRUE,
         updated_at = NOW()
     WHERE character_id = %s;
     """, (int(character_id),))
 
 
 def admin_add_card_character(
     character_id: int,
     character_name: str,
     anime_name: str,
     image_url: str = "",
 ):
     upsert_card_character_catalog(
         character_id=character_id,
         character_name=character_name,
         anime_name=anime_name,
         image_url=image_url,
     )
+
+
+def list_all_card_character_catalog() -> List[Dict[str, Any]]:
+    rows = _run(
+        """
+        SELECT
+            character_id,
+            character_name,
+            anime_name,
+            image_url
+        FROM card_characters_catalog
+        WHERE is_deleted = FALSE
+        ORDER BY anime_name ASC, character_name ASC;
+        """,
+        fetch="all",
+    )
+    return rows or []
 
EOF
)
