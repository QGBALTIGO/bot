from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

SP_TZ = ZoneInfo("America/Sao_Paulo")

DICE_INITIAL_BALANCE = 4
DICE_MAX_BALANCE = 24
DICE_RECHARGE_HOURS = (1, 4, 7, 10, 13, 16, 19, 22)
DICE_ROLL_TTL_MINUTES = 15


@dataclass(frozen=True)
class DailyReward:
    streak: int
    cycle_day: int
    coins: int
    dice: int
    spins: int


@dataclass(frozen=True)
class SpinReward:
    code: str
    label: str
    resource: str
    amount: int
    weight: int


SPIN_REWARDS: tuple[SpinReward, ...] = (
    SpinReward("coins_2", "+2 coins", "coins", 2, 22),
    SpinReward("coins_4", "+4 coins", "coins", 4, 18),
    SpinReward("dice_1", "+1 dado", "dice", 1, 18),
    SpinReward("coins_6", "+6 coins", "coins", 6, 14),
    SpinReward("dice_2", "+2 dados", "dice", 2, 10),
    SpinReward("coins_10", "+10 coins", "coins", 10, 8),
    SpinReward("spins_1", "+1 giro", "spins", 1, 6),
    SpinReward("jackpot", "+15 coins", "coins", 15, 4),
)


def now_sp() -> datetime:
    return datetime.now(SP_TZ)


def today_sp(now: datetime | None = None) -> date:
    current = now or now_sp()
    return current.astimezone(SP_TZ).date()


def daily_reward_for_streak(streak: int) -> DailyReward:
    streak = max(1, int(streak))
    cycle_day = ((streak - 1) % 7) + 1

    coins = 3
    dice = 1
    spins = 1

    if cycle_day == 3:
        coins += 2
    elif cycle_day == 5:
        coins += 3
        dice += 1
    elif cycle_day == 7:
        coins += 7
        dice += 1
        spins += 1

    return DailyReward(
        streak=streak,
        cycle_day=cycle_day,
        coins=coins,
        dice=dice,
        spins=spins,
    )


def next_streak(previous_claim_date: date | None, previous_streak: int, today: date) -> int:
    if previous_claim_date == today:
        return max(1, int(previous_streak or 1))
    if previous_claim_date == today - timedelta(days=1):
        return max(1, int(previous_streak or 0) + 1)
    return 1


def dice_slot_number(now: datetime | None = None) -> int:
    current = (now or now_sp()).astimezone(SP_TZ)
    hour = current.hour

    if hour < DICE_RECHARGE_HOURS[0]:
        base_date = current.date() - timedelta(days=1)
        slot_index = len(DICE_RECHARGE_HOURS) - 1
    else:
        base_date = current.date()
        slot_index = 0
        for idx, recharge_hour in enumerate(DICE_RECHARGE_HOURS):
            if recharge_hour <= hour:
                slot_index = idx
            else:
                break

    return base_date.toordinal() * len(DICE_RECHARGE_HOURS) + slot_index


def next_dice_recharge(now: datetime | None = None) -> datetime:
    current = (now or now_sp()).astimezone(SP_TZ)
    for hour in DICE_RECHARGE_HOURS:
        candidate = datetime(
            current.year,
            current.month,
            current.day,
            hour,
            0,
            0,
            tzinfo=SP_TZ,
        )
        if current < candidate:
            return candidate

    tomorrow = current.date() + timedelta(days=1)
    return datetime(
        tomorrow.year,
        tomorrow.month,
        tomorrow.day,
        DICE_RECHARGE_HOURS[0],
        0,
        0,
        tzinfo=SP_TZ,
    )


def recharged_dice_balance(balance: int, last_slot: int | None, current_slot: int) -> tuple[int, int]:
    balance = max(0, int(balance))
    current_slot = int(current_slot)

    if last_slot is None:
        return min(balance, DICE_MAX_BALANCE), current_slot

    last_slot = int(last_slot)
    if current_slot <= last_slot:
        return min(balance, DICE_MAX_BALANCE), last_slot

    gained = current_slot - last_slot
    return min(DICE_MAX_BALANCE, balance + gained), current_slot


def spin_total_weight(rewards: Iterable[SpinReward] = SPIN_REWARDS) -> int:
    return sum(max(0, int(item.weight)) for item in rewards)


def choose_spin_reward(ticket: int, rewards: tuple[SpinReward, ...] = SPIN_REWARDS) -> tuple[int, SpinReward]:
    total = spin_total_weight(rewards)
    if total <= 0:
        raise ValueError("spin reward table has no positive weight")

    ticket = int(ticket) % total
    cursor = 0
    for index, reward in enumerate(rewards):
        cursor += max(0, int(reward.weight))
        if ticket < cursor:
            return index, reward

    return len(rewards) - 1, rewards[-1]
