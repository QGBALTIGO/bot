import unittest

from termo_rules import daily_coin_reward, evaluate_guess, streak_bonus, valid_format


class TermoRulesTests(unittest.TestCase):
    def test_daily_reward_decreases_by_attempt(self):
        self.assertEqual([12, 10, 8, 6, 4, 2], [daily_coin_reward(i) for i in range(1, 7)])

    def test_streak_bonus_milestones(self):
        self.assertEqual(0, streak_bonus(2))
        self.assertEqual(5, streak_bonus(3))
        self.assertEqual(15, streak_bonus(7))
        self.assertEqual(50, streak_bonus(30))

    def test_evaluation_handles_duplicate_letters_without_overcounting(self):
        result = evaluate_guess("naruto", "banana")
        self.assertEqual(6, len(result))
        self.assertLessEqual(result.count("present") + result.count("correct"), 3)

    def test_word_format_requires_six_letters(self):
        self.assertTrue(valid_format("naruto"))
        self.assertFalse(valid_format("goku"))
        self.assertFalse(valid_format("naruto7"))


if __name__ == "__main__":
    unittest.main()
