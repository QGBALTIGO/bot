import unittest
from datetime import date, datetime

from game_rules import (
    DICE_MAX_BALANCE,
    SP_TZ,
    choose_spin_reward,
    daily_reward_for_streak,
    dice_slot_number,
    next_streak,
    recharged_dice_balance,
    spin_total_weight,
)


class DailyRulesTests(unittest.TestCase):
    def test_daily_always_grants_real_resources(self):
        for streak in range(1, 22):
            reward = daily_reward_for_streak(streak)
            self.assertGreaterEqual(reward.coins, 0)
            self.assertGreaterEqual(reward.dice, 0)
            self.assertGreaterEqual(reward.spins, 0)
            self.assertGreater(reward.coins + reward.dice + reward.spins, 0)

    def test_day_seven_is_stronger_than_day_one(self):
        day_one = daily_reward_for_streak(1)
        day_seven = daily_reward_for_streak(7)
        self.assertGreater(day_seven.coins, day_one.coins)
        self.assertGreaterEqual(day_seven.dice, day_one.dice)
        self.assertGreater(day_seven.spins, day_one.spins)

    def test_streak_increments_only_on_consecutive_day(self):
        today = date(2026, 8, 26)
        self.assertEqual(next_streak(date(2026, 8, 25), 4, today), 5)
        self.assertEqual(next_streak(date(2026, 8, 24), 4, today), 1)
        self.assertEqual(next_streak(today, 4, today), 4)


class DiceRulesTests(unittest.TestCase):
    def test_fixed_recharge_slots(self):
        at_midnight = datetime(2026, 8, 26, 0, 30, tzinfo=SP_TZ)
        at_one = datetime(2026, 8, 26, 1, 0, tzinfo=SP_TZ)
        at_four = datetime(2026, 8, 26, 4, 0, tzinfo=SP_TZ)
        self.assertLess(dice_slot_number(at_midnight), dice_slot_number(at_one))
        self.assertEqual(dice_slot_number(at_four), dice_slot_number(at_one) + 1)

    def test_recharge_never_exceeds_cap(self):
        balance, slot = recharged_dice_balance(23, 100, 110)
        self.assertEqual(balance, DICE_MAX_BALANCE)
        self.assertEqual(slot, 110)

    def test_no_recharge_when_slot_did_not_advance(self):
        balance, slot = recharged_dice_balance(8, 100, 100)
        self.assertEqual((balance, slot), (8, 100))


class SpinRulesTests(unittest.TestCase):
    def test_every_ticket_resolves_to_reward(self):
        total = spin_total_weight()
        self.assertGreater(total, 0)
        observed = set()
        for ticket in range(total):
            index, reward = choose_spin_reward(ticket)
            self.assertGreaterEqual(index, 0)
            self.assertGreater(reward.amount, 0)
            self.assertIn(reward.resource, {"coins", "dice", "spins"})
            observed.add(reward.code)
        self.assertGreater(len(observed), 1)

    def test_ticket_wraps_safely(self):
        total = spin_total_weight()
        first = choose_spin_reward(0)
        wrapped = choose_spin_reward(total)
        self.assertEqual(first, wrapped)


if __name__ == "__main__":
    unittest.main()
