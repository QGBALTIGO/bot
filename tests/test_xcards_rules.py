import unittest

from xcards_rules import is_market_eligible, parse_bp, tier_for_card


class XCardsRulesTests(unittest.TestCase):
    def test_parse_bp_accepts_numeric_text(self):
        self.assertEqual(3500, parse_bp("BP 3,500"))
        self.assertEqual(4000, parse_bp("4000"))
        self.assertEqual(0, parse_bp("-"))

    def test_tier_boundaries_are_stable(self):
        self.assertEqual("rookie", tier_for_card({"bp_value": 2000}).code)
        self.assertEqual("standard", tier_for_card({"bp_value": 2001}).code)
        self.assertEqual("advanced", tier_for_card({"bp_value": 3001}).code)
        self.assertEqual("elite", tier_for_card({"bp_value": 4001}).code)

    def test_market_requires_real_playable_card(self):
        self.assertTrue(is_market_eligible({"id": 10, "bp_value": 2500, "image": "https://img.test/card.jpg"}))
        self.assertFalse(is_market_eligible({"id": 10, "bp_value": 0, "image": "https://img.test/card.jpg"}))
        self.assertFalse(is_market_eligible({"id": 10, "bp_value": 2500, "image": ""}))
        self.assertFalse(is_market_eligible({"id": 0, "bp_value": 2500, "image": "https://img.test/card.jpg"}))


if __name__ == "__main__":
    unittest.main()
