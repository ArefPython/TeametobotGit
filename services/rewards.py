from typing import Dict, Any, List, Tuple
from datetime import datetime
from ..utils.time import now_local, parse_db_dt

OVERTIME_BANK_KEY = "overtime_minutes_bank"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _today_iso() -> str:
    return now_local().date().isoformat()

def _display_name(u: Dict[str, Any], fallback_id: str) -> str:
    return u.get("display_name") or u.get("username") or fallback_id

def _today_earliest_per_user(db: Dict[str, Any]) -> List[Tuple[str, datetime]]:
    """
    Return a list of (user_id, earliest_dt_today) sorted by time.
    Skips users with no check-in today or inactive users.
    """
    today = now_local().date()
    rows: List[Tuple[str, datetime]] = []

    for uid, u in db.items():
        if uid == "_config" or not isinstance(u, dict):
            continue
        if not u.get("active", False):   # 🔹 skip inactive users
            continue

        earliest: datetime | None = None
        for rec in u.get("check_ins", []):
            s = rec.get("datetime")
            if not s:
                continue
            dt = parse_db_dt(s)
            if dt.date() != today:
                continue
            if earliest is None or dt < earliest:
                earliest = dt
        if earliest is not None:
            rows.append((uid, earliest))

    rows.sort(key=lambda t: t[1])
    return rows

def build_early_birds_ladder(db: Dict[str, Any]) -> str:
    """
    Build the text ladder for today's top-4 earliest check-ins.
    Only counts active users.
    """
    order = _today_earliest_per_user(db)[:4]
    if not order:
        return "🐦 Early-birds Ladder (امروز)\n— هنوز کسی وارد نشده —"

    lines = ["🐦 Early-birds Ladder (امروز)"]
    for i, (uid, dt) in enumerate(order, start=1):
        u = db.get(uid, {})
        name = _display_name(u, uid)
        points = _safe_int(u.get("points", 0))
        price_value = points * 0.4
        price_str = f"{price_value:.2f}".rstrip('0').rstrip('.')
        lines.append(f"{i}. {name} - {dt.strftime('%H:%M')} ({points} pts | {price_str} $)")
    return "\n".join(lines)

async def handle_early_bird_logic(db: Dict[str, Any], user_id: str) -> bool:
    """
    If user is in today's top-4 and not yet rewarded, add +1 point.
    Skips inactive users.
    """
    u = db.setdefault(user_id, {})
    if not u.get("active", False):   # 🔹 skip inactive users
        return False

    today = _today_iso()
    order = _today_earliest_per_user(db)[:4]
    top_ids = [uid for uid, _ in order]

    if user_id not in top_ids:
        return False

    awarded = u.setdefault("top_awarded_dates", [])
    if today in awarded:
        return False

    u["points"] = _safe_int(u.get("points", 0)) + 1
    awarded.append(today)
    return True


def accrue_overtime_points(user: Dict[str, Any], minutes: int) -> Tuple[int, int]:
    """
    Add overtime minutes to the user's bank and convert full hours to points.
    Returns (points_added, remaining_minutes).
    """
    if minutes <= 0:
        return 0, _safe_int(user.get(OVERTIME_BANK_KEY, 0))

    bank = _safe_int(user.get(OVERTIME_BANK_KEY, 0)) + minutes
    points_added, remainder = divmod(bank, 60)
    user[OVERTIME_BANK_KEY] = remainder

    if points_added:
        user["points"] = _safe_int(user.get("points", 0)) + points_added

    return points_added, remainder
