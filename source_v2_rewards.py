from __future__ import annotations


def level_xp_required(level: int) -> int:
    level = max(1, int(level))
    return 80 * (level - 1) * (level - 1) + 120 * (level - 1)


def xp_to_level(xp: int) -> int:
    xp = max(0, int(xp))
    level = 1
    while xp >= level_xp_required(level + 1):
        level += 1
    return level


def ensure_reward_rows(cur, user_id: int) -> None:
    user_id = int(user_id)
    cur.execute(
        "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
        (user_id,),
    )
    cur.execute(
        """
        INSERT INTO user_progress (user_id, xp, level, total_actions)
        VALUES (%s, 0, 1, 0)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id,),
    )


def apply_reward_locked(cur, user_id: int, *, xp: int = 0, coins: int = 0) -> dict:
    """Apply Source Coins + XP using the existing canonical tables inside caller transaction."""

    user_id = int(user_id)
    reward_xp = max(0, int(xp or 0))
    reward_coins = max(0, int(coins or 0))
    ensure_reward_rows(cur, user_id)

    cur.execute(
        """
        UPDATE users
        SET coins = COALESCE(coins, 0) + %s,
            updated_at = NOW()
        WHERE user_id = %s
        RETURNING coins
        """,
        (reward_coins, user_id),
    )
    coins_row = cur.fetchone()
    coins_after = int((coins_row.get("coins") if isinstance(coins_row, dict) else coins_row[0]) if coins_row else 0)

    cur.execute("SELECT xp FROM user_progress WHERE user_id = %s FOR UPDATE", (user_id,))
    xp_row = cur.fetchone()
    old_xp = int((xp_row.get("xp") if isinstance(xp_row, dict) else xp_row[0]) if xp_row else 0)
    new_xp = old_xp + reward_xp
    new_level = xp_to_level(new_xp)
    cur.execute(
        """
        UPDATE user_progress
        SET xp = %s,
            level = %s,
            updated_at = NOW()
        WHERE user_id = %s
        """,
        (new_xp, new_level, user_id),
    )
    return {
        "coins_added": reward_coins,
        "coins_after": coins_after,
        "xp_added": reward_xp,
        "xp_after": new_xp,
        "level_after": new_level,
    }


def grant_character_locked(cur, user_id: int, character_id: int, *, quantity: int = 1) -> int:
    """Grant copies of an existing Source character ID; never creates a new character identity."""

    user_id = int(user_id)
    character_id = int(character_id)
    quantity = max(1, int(quantity or 1))
    cur.execute(
        """
        INSERT INTO user_card_collection
            (user_id, character_id, quantity, first_obtained_at, updated_at)
        VALUES (%s, %s, %s, NOW(), NOW())
        ON CONFLICT (user_id, character_id) DO UPDATE SET
            quantity = user_card_collection.quantity + EXCLUDED.quantity,
            updated_at = NOW()
        RETURNING quantity
        """,
        (user_id, character_id, quantity),
    )
    row = cur.fetchone()
    return int((row.get("quantity") if isinstance(row, dict) else row[0]) if row else quantity)
