import json
import asyncio
from typing import Any, Dict, Optional
from .config import DATA_FILE

_lock = asyncio.Lock()

DEFAULT_USER = {
    "username": "",
    "days": [],
    "yellow_cards": [],
    "check_ins": [],
    "check_outs": [],
    "tasks": [],
    "tasks_done": [],
    "display_name": "",
    "points": 0,
    "top_awarded_dates": [],
    "team_awarded_dates": [],
    "withdrawals": [],
    "active": False,   # 🔹 NEW: user is inactive by default
}

async def read_all() -> Dict[str, Any]:
    async with _lock:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

async def write_all(db: Dict[str, Any]) -> None:
    async with _lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

async def ensure_config(db: Dict[str, Any]) -> Dict[str, Any]:
    cfg = db.setdefault("_config", {})
    cfg.setdefault("unlimited_dates", [])
    cfg.setdefault("checkin_limit", None)  # None → use DEFAULT_CHECKIN_LIMIT
    return cfg

async def get_user(
    db: Dict[str, Any],
    uid: str,
    *,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> Dict[str, Any]:
    user = db.setdefault(uid, DEFAULT_USER.copy())
    if username is not None and user.get("username") != username:
        user["username"] = username
    if first_name is not None:
        user["first_name"] = first_name
    return user
