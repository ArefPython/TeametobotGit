from telegram import Update
from telegram.ext import ContextTypes
from ..storage import read_all, write_all, get_user
from ..services.attendance import append_check
from ..services.yellow_cards import maybe_add_yellow
from ..services.rewards import handle_early_bird_logic, build_early_birds_ladder
from ..utils.time import parse_db_dt   # 🔹 add this line

async def handle_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or f"user_{user_id}"

    db = await read_all()
    user = await get_user(db, user_id, username=username)
    if not user.get("active", False):
        return await update.message.reply_text("⛔️ حساب شما توسط مدیریت فعال نشده است.")

    # 🔹 check if already checked in today
    today = when = None
    from ..utils.time import now_local, parse_db_dt
    today = now_local().date()

    for rec in user.get("check_ins", []):
        dt = parse_db_dt(rec["datetime"])
        if dt.date() == today:
            return await update.message.reply_text(
                "⚠️ شما امروز یکبار ورود ثبت کرده‌اید و نمی‌توانید دوباره ورود بزنید."
            )

    # record first check-in of the day
    when = await append_check(db, user, kind="in")
    got_yellow = await maybe_add_yellow(db, user, when)

    just_awarded = await handle_early_bird_logic(db, user_id)
    ladder_text = build_early_birds_ladder(db)

    await write_all(db)

    time_str = when.strftime("%H:%M")
    display = user.get("display_name") or username

    # personal message
    if got_yellow:
        await update.message.reply_text(
            f"⏰ دیر کردی! کارت زرد گرفتی.\nولی ورودت در ساعت {time_str} ثبت شد ✅"
        )
    else:
        await update.message.reply_text(f"✅ ورود امروز در ساعت {time_str} ثبت شد.")

    if just_awarded:
        await update.message.reply_text("🏅 شما بین سه نفر اول امروز بودید؛ 1 امتیاز گرفتید!")

    await update.message.reply_text(ladder_text)

    # broadcast
    if got_yellow:
        text = f"📢 {display} در ساعت {time_str} وارد شد ❌ (کارت زرد گرفت)"
    else:
        text = f"📢 {display} در ساعت {time_str} وارد شد ✅"

    for uid in db:
        if uid == "_config":
            continue
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except Exception:
            pass


async def handle_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or f"user_{user_id}"

    db = await read_all()
    user = await get_user(db, user_id, username=username)
    if not user.get("active", False):
        return await update.message.reply_text("⛔️ حساب شما توسط مدیریت فعال نشده است.")

    # record checkout
    when = await append_check(db, user, kind="out")
    await write_all(db)

    # find the FIRST check-in today
    first_in = None
    for rec in user.get("check_ins", []):
        dt = parse_db_dt(rec["datetime"])
        if dt.date() == when.date():
            if not first_in or dt < first_in:
                first_in = dt

    worked_str = ""
    overtime_str = ""
    if first_in:
        delta = when - first_in
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        worked_str = f" و امروز جمعاً {hours} ساعت و {minutes} دقیقه کار کرد"

        # check for overtime past 18:00
        six_pm = when.replace(hour=18, minute=0, second=0, microsecond=0)
        if when > six_pm:
            overtime_delta = when - six_pm
            ov_minutes = overtime_delta.seconds // 60
            if ov_minutes > 0:
                overtime_str = f" و ایشون {ov_minutes} دقیقه اضافه در تلاش بودند"

    time_str = when.strftime("%H:%M")
    display = user.get("display_name") or username

    # 📢 broadcast to everyone
    text = f"📢 {display} در ساعت {time_str} خارج شد{worked_str}{overtime_str}."
    for uid in db:
        if uid == "_config":
            continue
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except Exception:
            pass
async def my_checkins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = await read_all()
    user = db.get(user_id)

    if not user or not user.get("check_ins"):
        return await update.message.reply_text("هیچ ورودی ثبت نشده است.")

    lines = ["📋 ورودهای شما:"]
    for rec in user.get("check_ins", [])[-10:]:  # show last 10
        lines.append(f"- {rec['datetime']}")
    await update.message.reply_text("\n".join(lines))


async def my_checkouts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = await read_all()
    user = db.get(user_id)

    if not user or not user.get("check_outs"):
        return await update.message.reply_text("هیچ خروجی ثبت نشده است.")

    lines = ["🏁 خروج‌های شما:"]
    for rec in user.get("check_outs", [])[-10:]:  # show last 10
        lines.append(f"- {rec['datetime']}")
    await update.message.reply_text("\n".join(lines))
async def my_yellow_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = await read_all()
    user = db.get(user_id)

    if not user or not user.get("yellow_cards"):
        return await update.message.reply_text("🎉 شما هیچ کارت زردی ندارید.")

    lines = ["📒 کارت‌های زرد شما:"]
    for rec in user.get("yellow_cards", [])[-10:]:  # show last 10
        lines.append(f"- {rec}")
    await update.message.reply_text("\n".join(lines))
