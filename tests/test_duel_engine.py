import unittest

from duel_engine import build_team_snapshot, get_alive_slots, is_team_eliminated, resolve_round


class DuelEngineTests(unittest.TestCase):
    def _cards(self, base_bp: int):
        return [
            {"id": 1, "name": "A", "title": "T", "bp_value": base_bp},
            {"id": 2, "name": "B", "title": "T", "bp_value": base_bp + 500},
            {"id": 3, "name": "C", "title": "T", "bp_value": base_bp + 1000},
        ]

    def test_higher_bp_damages_only_loser(self):
        team_a = build_team_snapshot(self._cards(3000))
        team_b = build_team_snapshot(self._cards(1000))
        result = resolve_round(team_a, 1, 10, team_b, 1, 20)
        self.assertEqual("a_win", result["outcome"])
        self.assertEqual(100, result["team_a"][0]["hp"])
        self.assertEqual(67, result["team_b"][0]["hp"])

    def test_tie_damages_both_cards(self):
        team_a = build_team_snapshot(self._cards(2000))
        team_b = build_team_snapshot(self._cards(2000))
        result = resolve_round(team_a, 1, 10, team_b, 1, 20)
        self.assertEqual("tie", result["outcome"])
        self.assertEqual(67, result["team_a"][0]["hp"])
        self.assertEqual(67, result["team_b"][0]["hp"])

    def test_three_losses_eliminate_slot(self):
        team_a = build_team_snapshot(self._cards(4000))
        team_b = build_team_snapshot(self._cards(1000))
        for _ in range(3):
            result = resolve_round(team_a, 1, 10, team_b, 1, 20)
            team_a, team_b = result["team_a"], result["team_b"]
        self.assertNotIn(1, get_alive_slots(team_b))
        self.assertFalse(is_team_eliminated(team_b))


if __name__ == "__main__":
    unittest.main()
