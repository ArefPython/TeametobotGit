from telegram import Update
from telegram.ext import ContextTypes
from ..storage import read_all
from ..config import BTN_SCORES

async def my_scores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = await read_all()
    user = db.get(user_id)

    # personal points
    my_points = int(user.get("points", 0)) if user else 0
    lines = [f"⭐️ شما {my_points} امتیاز دارید", ""]

    # team leaderboard
    scores = []
    for uid, u in db.items():
        if uid == "_config":
            continue
        pts = int(u.get("points", 0))
        name = u.get("display_name") or u.get("username") or uid
        scores.append((pts, name))

    scores.sort(key=lambda x: x[0], reverse=True)

    lines.append("🏆 جدول امتیازات (فصل جاری)")
    for rank, (pts, name) in enumerate(scores, start=1):
        lines.append(f"{rank}. {name} → {pts} امتیاز")

    await update.message.reply_text("\n".join(lines))
