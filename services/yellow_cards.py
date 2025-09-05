from datetime import datetime
from typing import Dict, Any
from ..utils.time import now_local
from .attendance import is_late

async def maybe_add_yellow(db: Dict[str, Any], user: Dict[str, Any], when: datetime) -> bool:
    """
    If the user is late, give them a yellow card.
    But only one yellow card per day is allowed.
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
    return True
