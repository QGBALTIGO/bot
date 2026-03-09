 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/commands/cards_admin.py b/commands/cards_admin.py
index d3653e98abbbf7ac0151a62e81ecc34591dbc5d5..c2f5d5cbbd151240e07be8a81a739717dd220bde 100644
--- a/commands/cards_admin.py
+++ b/commands/cards_admin.py
@@ -4,50 +4,55 @@ from telegram import Update
 from telegram.ext import ContextTypes
 
 from cards_service import (
     override_add_anime,
     override_add_character,
     override_add_subcategory,
     override_delete_anime,
     override_delete_character,
     override_delete_subcategory,
     override_set_anime_banner,
     override_set_anime_cover,
     override_set_character_image,
     override_set_character_name,
     override_subcategory_add_character,
     override_subcategory_remove_character,
     reload_cards_cache,
 )
 from utils.runtime_guard import lock_manager, rate_limiter
 
 CARD_ADMIN_IDS = {
     int(x.strip())
     for x in os.getenv("CARD_ADMIN_IDS", "").split(",")
     if x.strip().isdigit()
 }
 
+for fallback_var in ("BOT_OWNER_ID", "OWNER_ID", "ADMIN_ID"):
+    val = os.getenv(fallback_var, "").strip()
+    if val.isdigit():
+        CARD_ADMIN_IDS.add(int(val))
+
 CARD_ADMIN_USERNAMES = {
     x.strip().lower().lstrip("@")
     for x in os.getenv("CARD_ADMIN_USERNAMES", "").split(",")
     if x.strip()
 }
 
 ADMIN_RATE_LIMIT = int(os.getenv("ADMIN_RATE_LIMIT", "12"))
 ADMIN_RATE_WINDOW_SECONDS = float(os.getenv("ADMIN_RATE_WINDOW_SECONDS", "10"))
 
 
 def _is_admin(update: Update) -> bool:
     user = update.effective_user
     if not user:
         return False
 
     if user.id in CARD_ADMIN_IDS:
         return True
 
     username = (user.username or "").strip().lower().lstrip("@")
     if username and username in CARD_ADMIN_USERNAMES:
         return True
 
     return False
 
 
 
EOF
)
