from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple, Iterator

from ..utils.time import now_local, parse_hhmm, parse_db_dt
from ..storage import ensure_config
from ..config import DEFAULT_CHECKIN_LIMIT


RecordResult = Tuple[bool, str, Optional[datetime]]


async def effective_limit_str(db: Dict[str, Any]) -> str:
    cfg = await ensure_config(db)
    return cfg.get("checkin_limit") or DEFAULT_CHECKIN_LIMIT


async def is_unlimited_today(db: Dict[str, Any]) -> bool:
    cfg = await ensure_config(db)
    today = now_local().date().isoformat()
    return today in cfg.get("unlimited_dates", [])


async def is_late(db, when: datetime) -> bool:
    if await is_unlimited_today(db):
        return False
    weekday = when.weekday()
    if weekday == 3:
        limit_time = parse_hhmm("09:30")
    else:
        limit_time = parse_hhmm(await effective_limit_str(db))
    return when.time() > limit_time


def _today_local_date() -> date:
    return now_local().date()


def _iter_checks_for_day(user: Dict[str, Any], key: str, day: date) -> Iterator[datetime]:
    for rec in user.get(key, []):
        dt_str = rec.get("datetime")
        if not dt_str:
            continue
        try:
            dt = parse_db_dt(dt_str)
        except (ValueError, TypeError, KeyError):
            continue
        if dt.date() == day:
            yield dt


def has_checked_in_today(user: Dict[str, Any]) -> bool:
    today = _today_local_date()
    return any(_iter_checks_for_day(user, "check_ins", today))


def has_checked_out_today(user: Dict[str, Any]) -> bool:
    today = _today_local_date()
    return any(_iter_checks_for_day(user, "check_outs", today))


def first_check_in_for_day(user: Dict[str, Any], day: date) -> Optional[datetime]:
    first: Optional[datetime] = None
    for dt in _iter_checks_for_day(user, "check_ins", day):
        if first is None or dt < first:
            first = dt
    return first


async def record_check_in(db: Dict[str, Any], user: Dict[str, Any]) -> RecordResult:
    if has_checked_in_today(user):
        return False, "⚠️ شما امروز یکبار ورود ثبت کرده‌اید و نمی‌توانید دوباره ورود بزنید.", None

    when = await append_check(db, user, kind="in")
    return True, "ورود ثبت شد.", when


async def record_check_out(db: Dict[str, Any], user: Dict[str, Any]) -> RecordResult:
    if has_checked_out_today(user):
        return False, "⚠️ شما امروز یکبار خروج ثبت کرده‌اید و نمی‌توانید دوباره خروج بزنید.", None
    if not has_checked_in_today(user):
        return False, "ابتدا ورود بزنید، سپس خروج.", None

    when = await append_check(db, user, kind="out")
    return True, "خروج ثبت شد.", when


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
