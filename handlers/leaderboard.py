from telegram import Update
from telegram.ext import ContextTypes

from ..storage import read_all


def _msg(update: Update):
    return update.effective_message


def _user(update: Update):
    return update.effective_user




def _format_price(points: int) -> str:
    value = points * 0.4
    price_str = f"{value:.2f}".rstrip('0').rstrip('.')
    return price_str

async def my_scores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    db = await read_all()
    user = db.get(user_id)

    my_points = int(user.get("points", 0)) if user else 0
    my_price = _format_price(my_points)
    lines = [f"امتیاز شما {my_points} امتیاز است ({my_price} $)", ""]

    scores = []
    for uid, u in db.items():
        if uid == "_config":
            continue
        pts = int(u.get("points", 0))
        name = u.get("display_name") or u.get("username") or uid
        scores.append((pts, name))

    scores.sort(key=lambda x: x[0], reverse=True)

    lines.append("لیگ امتیازات تیمی (بر اساس امتیاز)")
    for rank, (pts, name) in enumerate(scores, start=1):
        price = _format_price(pts)
        lines.append(f"{rank}. {name} – {pts} امتیاز ({price} $)")

    await msg.reply_text("\n".join(lines))
