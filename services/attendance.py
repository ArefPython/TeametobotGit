from datetime import datetime
from typing import Dict, Any
from ..utils.time import now_local, parse_hhmm
from ..storage import ensure_config
from ..config import DEFAULT_CHECKIN_LIMIT

async def effective_limit_str(db: Dict[str, Any]) -> str:
    cfg = await ensure_config(db)
    return cfg.get("checkin_limit") or DEFAULT_CHECKIN_LIMIT

async def is_unlimited_today(db: Dict[str, Any]) -> bool:
    cfg = await ensure_config(db)
    today = now_local().date().isoformat()
    return today in cfg.get("unlimited_dates", [])

async def is_late(db: Dict[str, Any], when: datetime) -> bool:
    if await is_unlimited_today(db):
        return False
    limit = parse_hhmm(await effective_limit_str(db))
    return when.time() > limit

async def append_check(db: Dict[str, Any], user: Dict[str, Any], *, kind: str) -> datetime:
    now = now_local()
    ts = now.strftime("%Y-%m-%d %H:%M")
    rec = {"datetime": ts}
    if kind == "in":
        user.setdefault("check_ins", []).append(rec)
    elif kind == "out":
        user.setdefault("check_outs", []).append(rec)
    else:
        raise ValueError("kind must be 'in' or 'out'")
    return now
