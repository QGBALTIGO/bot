import unittest

from memory_rules import level_config, normalize_level


class MemoryRulesTests(unittest.TestCase):
    def test_portuguese_aliases(self):
        self.assertEqual("easy", normalize_level("fácil"))
        self.assertEqual("medium", normalize_level("Médio"))
        self.assertEqual("hard", normalize_level("difícil"))
        self.assertEqual("extreme", normalize_level("muito difícil"))

    def test_unknown_level_falls_back_to_medium(self):
        self.assertEqual("medium", normalize_level("qualquer"))

    def test_difficulty_scales_pair_count_and_plausible_time(self):
        levels = [level_config(code) for code in ("easy", "medium", "hard", "extreme")]
        self.assertEqual([4, 6, 8, 10], [item.pairs for item in levels])
        self.assertEqual(sorted(item.min_seconds for item in levels), [item.min_seconds for item in levels])


if __name__ == "__main__":
    unittest.main()
