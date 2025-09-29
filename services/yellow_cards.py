from datetime import datetime
from typing import Dict, Any
from ..utils.time import now_local
from .attendance import is_late

YELLOW_CARD_PENALTY = 2


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

async def maybe_add_yellow(db: Dict[str, Any], user: Dict[str, Any], when: datetime) -> bool:
    """
    If the user is late, give them a yellow card and apply the point penalty.
    Only one yellow card per day is allowed.
    Returns True if a new card was given.
    """
    if not await is_late(db, when):
        return False

    today = now_local().date().isoformat()
    cards = user.setdefault("yellow_cards", [])

    # check if user already has a card for today
    for rec in cards:
        if today in rec:   # rec is "تاخیر در ورود در YYYY-MM-DD HH:MM"
            return False

    msg = f"تاخیر در ورود در {when.strftime('%Y-%m-%d %H:%M')}"
    cards.append(msg)

    current_points = _safe_int(user.get("points", 0))
    user["points"] = current_points - YELLOW_CARD_PENALTY
    return True
