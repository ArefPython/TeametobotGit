from datetime import datetime, date, time, timedelta
from typing import Tuple
from .. import config

def now_local() -> datetime:
    return datetime.now(config.LOCAL_TZ)

def today_range() -> Tuple[datetime, datetime]:
    n = now_local()
    start = n.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end

def parse_hhmm(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))

def parse_db_dt(s: str) -> datetime:
    """
    Parse 'YYYY-MM-DD HH:MM' (stored in JSON) into a timezone-aware datetime.
    """
    naive = datetime.strptime(s, "%Y-%m-%d %H:%M")
    return config.LOCAL_TZ.localize(naive)
