from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Tuple


TEAM_SIZE = 3
DEFAULT_HP = 100
HP_BY_LOSS_COUNT = (100, 67, 34, 0)


def parse_bp_value(raw_value: Any) -> int:
    text = str(raw_value or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        try:
            return int(digits)
        except Exception:
            return 0
    return 0


def normalize_mode(raw_mode: Any) -> str:
    mode = str(raw_mode or "").strip().lower()
    if mode in {"apostado", "wager", "stake"}:
        return "wager"
    return "friendly"


def build_team_entry(card: Dict[str, Any], slot: int) -> Dict[str, Any]:
    bp_value = int(card.get("bp_value") or parse_bp_value(card.get("bp") or card.get("pa")))
    return {
        "slot": int(slot),
        "card_id": int(card.get("card_id") or card.get("id") or 0),
        "card_no": str(card.get("card_no") or "").strip(),
        "name": str(card.get("name") or "XCARD").strip(),
        "title": str(card.get("title") or card.get("anime") or "Obra desconhecida").strip(),
        "image": str(card.get("image") or "").strip(),
        "rarity": str(card.get("rarity") or card.get("raridade") or "-").strip(),
        "bp": int(bp_value),
        "bp_display": str(card.get("bp_display") or card.get("bp") or card.get("pa") or bp_value).strip(),
        "hp": DEFAULT_HP,
        "losses": 0,
        "eliminated": False,
    }


def build_team_snapshot(cards: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    snapshot: List[Dict[str, Any]] = []
    for index, card in enumerate(list(cards)[:TEAM_SIZE], start=1):
        snapshot.append(build_team_entry(card, index))
    return snapshot


def get_alive_slots(team: Iterable[Dict[str, Any]]) -> List[int]:
    alive: List[int] = []
    for entry in team:
        if not bool(entry.get("eliminated")) and int(entry.get("hp") or 0) > 0:
            alive.append(int(entry.get("slot") or 0))
    return sorted(slot for slot in alive if slot > 0)


def is_team_eliminated(team: Iterable[Dict[str, Any]]) -> bool:
    return len(get_alive_slots(team)) == 0


def find_team_entry(team: Iterable[Dict[str, Any]], slot: int) -> Optional[Dict[str, Any]]:
    target = int(slot)
    for entry in team:
        if int(entry.get("slot") or 0) == target:
            return entry
    return None


def validate_team_selection(card_ids: Iterable[Any]) -> Tuple[bool, str]:
    normalized: List[int] = []
    for raw_card_id in list(card_ids):
        card_id = int(raw_card_id or 0)
        if card_id <= 0:
            return False, "card_invalido"
        normalized.append(card_id)

    if len(normalized) != TEAM_SIZE:
        return False, "time_incompleto"

    if len(set(normalized)) != TEAM_SIZE:
        return False, "card_duplicado"

    return True, ""


def _hp_from_losses(loss_count: int) -> int:
    safe_loss_count = max(0, min(int(loss_count or 0), 3))
    return int(HP_BY_LOSS_COUNT[safe_loss_count])


def apply_round_loss(entry: Dict[str, Any]) -> Dict[str, Any]:
    updated = deepcopy(entry)
    losses = min(int(updated.get("losses") or 0) + 1, 3)
    updated["losses"] = losses
    updated["hp"] = _hp_from_losses(losses)
    updated["eliminated"] = bool(losses >= 3 or int(updated["hp"]) <= 0)
    return updated


def clone_team(team: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [deepcopy(entry) for entry in team]


def replace_team_entry(team: Iterable[Dict[str, Any]], updated_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    slot = int(updated_entry.get("slot") or 0)
    replaced: List[Dict[str, Any]] = []
    for entry in team:
        if int(entry.get("slot") or 0) == slot:
            replaced.append(deepcopy(updated_entry))
        else:
            replaced.append(deepcopy(entry))
    return replaced


def resolve_round(
    team_a: Iterable[Dict[str, Any]],
    slot_a: int,
    user_a: int,
    team_b: Iterable[Dict[str, Any]],
    slot_b: int,
    user_b: int,
) -> Dict[str, Any]:
    current_team_a = clone_team(team_a)
    current_team_b = clone_team(team_b)

    entry_a = find_team_entry(current_team_a, slot_a)
    entry_b = find_team_entry(current_team_b, slot_b)
    if not entry_a or not entry_b:
        raise ValueError("slot_invalido")
    if bool(entry_a.get("eliminated")) or int(entry_a.get("hp") or 0) <= 0:
        raise ValueError("slot_a_eliminado")
    if bool(entry_b.get("eliminated")) or int(entry_b.get("hp") or 0) <= 0:
        raise ValueError("slot_b_eliminado")

    bp_a = int(entry_a.get("bp") or 0)
    bp_b = int(entry_b.get("bp") or 0)
    before_a = deepcopy(entry_a)
    before_b = deepcopy(entry_b)

    outcome = "tie"
    winner_user_id: Optional[int] = None
    loser_user_id: Optional[int] = None
    note = "Choque equilibrado: os dois personagens perderam 33% de vida."

    if bp_a > bp_b:
        outcome = "a_win"
        winner_user_id = int(user_a)
        loser_user_id = int(user_b)
        entry_b = apply_round_loss(entry_b)
        note = "O personagem com maior BP venceu a rodada."
    elif bp_b > bp_a:
        outcome = "b_win"
        winner_user_id = int(user_b)
        loser_user_id = int(user_a)
        entry_a = apply_round_loss(entry_a)
        note = "O personagem com maior BP venceu a rodada."
    else:
        entry_a = apply_round_loss(entry_a)
        entry_b = apply_round_loss(entry_b)

    current_team_a = replace_team_entry(current_team_a, entry_a)
    current_team_b = replace_team_entry(current_team_b, entry_b)

    return {
        "outcome": outcome,
        "winner_user_id": winner_user_id,
        "loser_user_id": loser_user_id,
        "team_a": current_team_a,
        "team_b": current_team_b,
        "choice_a": {
            "slot": int(slot_a),
            "before": before_a,
            "after": deepcopy(entry_a),
        },
        "choice_b": {
            "slot": int(slot_b),
            "before": before_b,
            "after": deepcopy(entry_b),
        },
        "note": note,
    }


def choose_reward_card(team: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    cards = [deepcopy(entry) for entry in team]
    if not cards:
        return None

    cards.sort(
        key=lambda entry: (
            int(entry.get("bp") or 0),
            int(entry.get("hp") or 0),
            int(entry.get("slot") or 0),
            int(entry.get("card_id") or 0),
        )
    )
    return cards[0]


def hp_bar(entry: Dict[str, Any]) -> str:
    losses = int(entry.get("losses") or 0)
    safe_losses = max(0, min(losses, 3))
    active = max(0, 3 - safe_losses)
    return ("●" * active) + ("○" * safe_losses)


def format_team_lines(team: Iterable[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for entry in sorted(team, key=lambda item: int(item.get("slot") or 0)):
        slot = int(entry.get("slot") or 0)
        name = str(entry.get("name") or "XCARD").strip()
        bp = int(entry.get("bp") or 0)
        hp = int(entry.get("hp") or 0)
        status = "eliminado" if bool(entry.get("eliminated")) or hp <= 0 else "ativo"
        lines.append(
            f"{slot}. {name} | BP {bp} | Vida {hp}% {hp_bar(entry)} | {status}"
        )
    return lines

