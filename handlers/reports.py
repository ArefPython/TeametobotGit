import calendar
import os
import tempfile
from datetime import datetime
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import Update
from telegram.ext import ContextTypes

from ..storage import read_all
from ..utils.time import now_local, parse_db_dt


def _safe_parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return parse_db_dt(value)
    except Exception:
        return None


async def send_monthly_activity_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    db = await read_all()
    now = now_local()
    year = now.year
    month = now.month
    days_in_month = calendar.monthrange(year, month)[1]

    ins_counts = [0] * days_in_month
    outs_counts = [0] * days_in_month

    for uid, user in db.items():
        if uid == "_config":
            continue
        for rec in user.get("check_ins", []):
            dt = _safe_parse_dt(rec.get("datetime"))
            if dt and dt.year == year and dt.month == month:
                ins_counts[dt.day - 1] += 1
        for rec in user.get("check_outs", []):
            dt = _safe_parse_dt(rec.get("datetime"))
            if dt and dt.year == year and dt.month == month:
                outs_counts[dt.day - 1] += 1

    total_ins = sum(ins_counts)
    total_outs = sum(outs_counts)

    if total_ins == 0 and total_outs == 0:
        await message.reply_text("No check-ins or check-outs recorded this month yet.")
        return

    x_values = list(range(days_in_month))
    width = 0.4
    ins_positions = [x - width / 2 for x in x_values]
    outs_positions = [x + width / 2 for x in x_values]
    labels = [str(day) for day in range(1, days_in_month + 1)]

    month_label = now.strftime("%B %Y")

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(ins_positions, ins_counts, width, label="Check-ins", color="#1f77b4")
    ax.bar(outs_positions, outs_counts, width, label="Check-outs", color="#ff7f0e")
    ax.set_xticks(x_values)
    ax.set_xticklabels(labels, rotation=45)
    ax.set_xlabel("Day of Month")
    ax.set_ylabel("Number of Events")
    ax.set_title(f"Monthly Check-in/Check-out Overview ({month_label})")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()

    caption = f"{month_label}\nCheck-ins: {total_ins} | Check-outs: {total_outs}"

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        fig.savefig(tmp_file.name, dpi=150)
        tmp_path = tmp_file.name

    plt.close(fig)

    try:
        with open(tmp_path, "rb") as photo:
            await message.reply_photo(photo=photo, caption=caption)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
