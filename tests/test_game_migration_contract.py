from pathlib import Path
import unittest


class GameMigrationContractTests(unittest.TestCase):
    def test_legacy_coins_are_clamped_before_wallet_insert(self):
        source = Path("game_repository.py").read_text(encoding="utf-8")
        self.assertIn(
            'coins_sql = "GREATEST(0, COALESCE(coins, 0))" if has_coins else "0"',
            source,
        )

    def test_legacy_dice_are_clamped_to_v2_domain(self):
        source = Path("game_repository.py").read_text(encoding="utf-8")
        self.assertIn("GREATEST(0, COALESCE(dado_balance", source)
        self.assertIn("LEAST(", source)


if __name__ == "__main__":
    unittest.main()
