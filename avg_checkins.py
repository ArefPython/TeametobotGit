"""
Average check-in time command for python-telegram-bot v20+.

This module exposes:
    * compute_avg_checkins(...) - pure helper for aggregation
    * avgcheckins(...) - async PTB command handler
    * main() - wiring helper to run the bot with TELEGRAM_BOT_TOKEN

The command reads worker attendance data from the JSON file pointed to by
WORKERS_JSON (falls back to ./workers_datas.json) and replies with a sorted
leaderboard of average check-in times over a configurable rolling window.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

logger = logging.getLogger(__name__)

DATA_ENV_VAR = "WORKERS_JSON"
DEFAULT_DATA_PATH = "./worker_days_off.json"
DEFAULT_DAYS = 30
DEFAULT_EXCLUDE_USERS: Set[str] = {"Mfahime"}
DEFAULT_EXCLUDE_WEEKDAYS: Set[int] = {3}  # Thursday
TELEGRAM_SOFT_LIMIT = 3900  # keep well below hard 4096 cap

WEEKDAY_NAME_MAP = {
    0: "Mon",
    1: "Tue",
    2: "Wed",
    3: "Thu",
    4: "Fri",
    5: "Sat",
    6: "Sun",
}

WEEKDAY_NAME_MAP_FA = {
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنج‌شنبه",
    4: "جمعه",
    5: "شنبه",
    6: "یکشنبه",
}

WEEKDAY_TOKEN_MAP = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "weds": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}

PERSIAN_DIGIT_TABLE = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

USAGE_LINES = [
    "Usage parameters:",
    "days=<int>: window size, default 30. Example: days=21",
    "exclude_users=<comma_separated>: usernames to skip; merged with default. Example: exclude_users=Mfahime,TestUser",
    "exclude_weekdays=<comma_separated>: names or numbers; accept thu,thursday,3. Multiple allowed. Example: exclude_weekdays=fri,6",
    "limit=<int>: show only top N rows (default: show all).",
    "fa=1: output in Persian labels but keep times formatted HH:MM (e.g., ۰۸:۰۴).",
]


@dataclass
class CommandOptions:
    """Structured command options with sensible defaults."""

    days: int = DEFAULT_DAYS
    exclude_users: Set[str] = None  # type: ignore[assignment]
    exclude_weekdays: Set[int] = None  # type: ignore[assignment]
    limit: Optional[int] = None
    use_persian: bool = False

    def __post_init__(self) -> None:
        if self.exclude_users is None:
            self.exclude_users = set(DEFAULT_EXCLUDE_USERS)
        if self.exclude_weekdays is None:
            self.exclude_weekdays = set(DEFAULT_EXCLUDE_WEEKDAYS)


class WorkersDataError(Exception):
    """Raised when the attendance JSON cannot be read or parsed."""


def get_data_path() -> str:
    """Resolve the attendance JSON path from environment with fallback."""
    return os.getenv(DATA_ENV_VAR, DEFAULT_DATA_PATH)


def load_workers(path: str) -> Dict[str, Dict[str, object]]:
    """Load the workers JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise WorkersDataError(f"Data file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkersDataError(f"Invalid JSON content in {path}") from exc

    if not isinstance(data, dict):
        raise WorkersDataError("Top-level JSON structure must be an object.")
    return data


def resolve_weekday_token(token: str) -> int:
    """Convert a weekday token to Python weekday index (Mon=0)."""
    normalized = token.strip().lower()
    if not normalized:
        raise ValueError("Empty weekday token.")
    if normalized in WEEKDAY_TOKEN_MAP:
        return WEEKDAY_TOKEN_MAP[normalized]
    if normalized.isdigit():
        value = int(normalized)
        if 0 <= value <= 6:
            return value
    raise ValueError(f"Unrecognised weekday token: {token}")


def parse_command_args(args: Sequence[str]) -> CommandOptions:
    """Parse /avgcheckins arguments into CommandOptions."""
    options = CommandOptions()
    for raw in args:
        if "=" not in raw:
            raise ValueError(f"Expected key=value pairs, got '{raw}'.")
        key, value = raw.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "days":
            if not value.isdigit():
                raise ValueError("days must be a positive integer.")
            days = int(value)
            if days <= 0:
                raise ValueError("days must be greater than zero.")
            options.days = days
        elif key == "exclude_users":
            if value:
                users = {item.strip() for item in value.split(",") if item.strip()}
                options.exclude_users.update(users)
        elif key == "exclude_weekdays":
            if value:
                weekdays: Set[int] = set()
                for token in value.split(","):
                    token = token.strip()
                    if not token:
                        continue
                    weekdays.add(resolve_weekday_token(token))
                options.exclude_weekdays.update(weekdays)
        elif key == "limit":
            if not value.isdigit():
                raise ValueError("limit must be a positive integer.")
            limit = int(value)
            if limit <= 0:
                raise ValueError("limit must be greater than zero.")
            options.limit = limit
        elif key == "fa":
            options.use_persian = value in {"1", "true", "yes", "on"}
        else:
            raise ValueError(f"Unknown option '{key}'.")
    return options


def parse_checkin_datetime(value: str) -> Optional[datetime]:
    """Parse a check-in datetime string in '%Y-%m-%d %H:%M' format."""
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        logger.debug("Skipping malformed datetime '%s'.", value)
        return None


def compute_avg_checkins(
    path: str,
    days: int,
    exclude_users: Iterable[str],
    exclude_weekdays: Iterable[int],
) -> List[Tuple[str, float]]:
    """
    Compute per-user average check-in hour (as float hours) over the given window.
    """
    data = load_workers(path)
    threshold = datetime.now() - timedelta(days=days)
    excluded_usernames = set(exclude_users)
    excluded_weekday_set = set(exclude_weekdays)
    results: List[Tuple[str, float]] = []

    for uid, record in data.items():
        if not isinstance(record, dict):
            logger.debug("Skipping non-dict record for key '%s'.", uid)
            continue
        username = str(record.get("username") or f"user_{uid}")
        if username in excluded_usernames:
            continue
        check_ins = record.get("check_ins")
        if not isinstance(check_ins, list):
            continue

        minutes: List[int] = []
        for entry in check_ins:
            if not isinstance(entry, dict):
                continue
            dt_raw = entry.get("datetime")
            if not isinstance(dt_raw, str):
                continue
            dt = parse_checkin_datetime(dt_raw)
            if dt is None:
                continue
            if dt < threshold:
                continue
            if dt.weekday() in excluded_weekday_set:
                continue
            minutes.append(dt.hour * 60 + dt.minute)

        if not minutes:
            continue

        avg_minutes = sum(minutes) / float(len(minutes))
        avg_hours = avg_minutes / 60.0
        results.append((username, avg_hours))

    results.sort(key=lambda item: item[1])
    return results


def to_persian_digits(text: str) -> str:
    """Replace ASCII digits with Persian digits."""
    return text.translate(PERSIAN_DIGIT_TABLE)


def format_time(avg_hours: float, use_persian: bool = False) -> str:
    """Format average time as HH:MM AM/PM (or 24h with Persian digits)."""
    total_minutes = int(round(avg_hours * 60))
    total_minutes %= 24 * 60
    hours = total_minutes // 60
    minutes = total_minutes % 60

    if use_persian:
        return to_persian_digits(f"{hours:02d}:{minutes:02d}")

    dt = datetime(2000, 1, 1, hours, minutes)
    return dt.strftime("%I:%M %p")


def format_weekday_labels(days: Iterable[int], use_persian: bool) -> str:
    """Return a human-readable weekday exclusion summary."""
    src_map = WEEKDAY_NAME_MAP_FA if use_persian else WEEKDAY_NAME_MAP
    names: List[str] = []
    for day in sorted(set(days)):
        names.append(src_map.get(day, str(day)))
    if not names:
        return "بدون فیلتر روز هفته" if use_persian else "no weekday filter"
    joined = "، ".join(names) if use_persian else ", ".join(names)
    return f"{joined} حذف" if use_persian else f"{joined} excluded"


def format_excluded_users(users: Iterable[str], use_persian: bool) -> Optional[str]:
    """Format excluded user information if any are configured."""
    usernames = sorted({user for user in users})
    if not usernames:
        return None
    label = "کاربران حذف‌شده" if use_persian else "Excluded users"
    line = f"{label}: {', '.join(usernames)}"
    return to_persian_digits(line) if use_persian else line


def build_leaderboard_lines(
    entries: Sequence[Tuple[str, float]],
    use_persian: bool,
) -> List[str]:
    """Create aligned leaderboard lines."""
    arrow = "→"
    lines: List[str] = []
    width = 18
    for index, (username, avg_hours) in enumerate(entries, start=1):
        display_name = username if len(username) <= width else username[: width - 3] + "..."
        padded_name = display_name.ljust(width)
        index_label = to_persian_digits(str(index)) if use_persian else str(index)
        time_str = format_time(avg_hours, use_persian=use_persian)
        if use_persian:
            line = f"{index_label}. {padded_name} {arrow} {time_str}"
            lines.append(line)
        else:
            line = f"{index_label}. {padded_name} {arrow} {time_str}"
            lines.append(line)
    return lines


def assemble_message(
    header: str,
    score_lines: List[str],
    suffix_lines: List[str],
    hidden_count: int,
    use_persian: bool,
    excluded_users_line: Optional[str],
) -> str:
    """Combine all pieces into a single message within Telegram size limits."""
    prefix_lines = [header]
    if excluded_users_line:
        prefix_lines.append(excluded_users_line)
    prefix_lines.append("")

    trimmed_scores = list(score_lines)
    total_hidden = hidden_count
    while trimmed_scores and len("\n".join(prefix_lines + trimmed_scores + suffix_lines)) > TELEGRAM_SOFT_LIMIT:
        trimmed_scores.pop()
        total_hidden += 1

    lines = prefix_lines + trimmed_scores
    if total_hidden > 0:
        more_line = f"... (+{total_hidden} more)"
        if use_persian:
            more_line = to_persian_digits(more_line)
        lines.append(more_line)

    if suffix_lines:
        if lines and lines[-1] != "" and suffix_lines[0] != "":
            lines.append("")
        lines.extend(suffix_lines)

    combined = "\n".join(lines)
    if len(combined) <= TELEGRAM_SOFT_LIMIT:
        return combined

    # Fallback: trim suffix lines if still too long.
    trimmed_suffix = list(suffix_lines)
    while trimmed_suffix and len("\n".join(prefix_lines + trimmed_scores + trimmed_suffix)) > TELEGRAM_SOFT_LIMIT:
        trimmed_suffix.pop()
    lines = prefix_lines + trimmed_scores
    if total_hidden > 0:
        more_line = f"... (+{total_hidden} more)"
        if use_persian:
            more_line = to_persian_digits(more_line)
        lines.append(more_line)
    lines.extend(trimmed_suffix)
    combined = "\n".join(lines)
    if len(combined) > TELEGRAM_SOFT_LIMIT:
        combined = combined[: TELEGRAM_SOFT_LIMIT - 1]
    return combined


async def avgcheckins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram command handler for /avgcheckins."""
    message = update.effective_message
    if message is None:
        return

    args = context.args or []
    try:
        options = parse_command_args(args)
    except ValueError as exc:
        usage = "\n".join(USAGE_LINES)
        await message.reply_text(f"Invalid arguments: {exc}\n\n{usage}")
        return

    data_path = get_data_path()
    try:
        results = compute_avg_checkins(
            data_path,
            options.days,
            options.exclude_users,
            options.exclude_weekdays,
        )
    except WorkersDataError as exc:
        await message.reply_text(str(exc))
        return

    if not results:
        await message.reply_text("No check-ins found in the selected window after filters.")
        return

    display_entries = results
    hidden_count = 0
    if options.limit is not None and options.limit < len(results):
        display_entries = results[: options.limit]
        hidden_count = len(results) - len(display_entries)

    exclude_desc = format_weekday_labels(options.exclude_weekdays, options.use_persian)
    if options.use_persian:
        header = f"میانگین ورود ({to_persian_digits(str(options.days))} روز اخیر، {exclude_desc})"
    else:
        header = f"Average Check-ins (last {options.days} days, {exclude_desc})"

    excluded_users_line = format_excluded_users(
        options.exclude_users,
        options.use_persian,
    )
    if not args:
        usage_lines = USAGE_LINES
        if options.use_persian:
            usage_lines = [to_persian_digits(line) for line in usage_lines]
        suffix_lines = [""] + usage_lines
    else:
        suffix_lines = []

    score_lines = build_leaderboard_lines(display_entries, options.use_persian)
    response = assemble_message(
        header=header,
        score_lines=score_lines,
        suffix_lines=suffix_lines,
        hidden_count=hidden_count,
        use_persian=options.use_persian,
        excluded_users_line=excluded_users_line,
    )
    await message.reply_text(response)


def build_application(token: str) -> Application:
    """Build a PTB application with the /avgcheckins command registered."""
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("avgcheckins", avgcheckins))
    return application


def main() -> None:
    """Entry point for running the Telegram bot."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required to run the bot.")
    app = build_application(token)
    app.run_polling()


def _print_sanity(limit: int) -> None:
    """Print a quick leaderboard preview to stdout for sanity checks."""
    path = get_data_path()
    try:
        results = compute_avg_checkins(
            path,
            DEFAULT_DAYS,
            DEFAULT_EXCLUDE_USERS,
            DEFAULT_EXCLUDE_WEEKDAYS,
        )
    except WorkersDataError as exc:
        print(f"[error] {exc}")
        return

    subset = results[:limit]
    if not subset:
        print("No results available.")
        return
    print(f"Average check-ins preview (top {limit}):")
    for index, (username, avg_hours) in enumerate(subset, start=1):
        minutes = int(round(avg_hours * 60))
        print(f"{index}. {username:<18} -> {format_time(avg_hours)} (minutes={minutes})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Average check-in command utility.")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Print a sample leaderboard instead of running the bot.")
    parser.add_argument("--limit", type=int, default=5, help="Limit for the sample leaderboard when using --print (default: 5).")
    args = parser.parse_args()

    if args.print_only:
        _print_sanity(limit=max(1, args.limit))
    else:
        main()
