from telegram import Update
from telegram.ext import CallbackContext, ContextTypes

from ..storage import read_all, write_all, get_user
from ..services.attendance import (
    record_check_in,
    record_check_out,
    first_check_in_for_day,
)
from ..services.yellow_cards import maybe_add_yellow
from ..services.rewards import (
    handle_early_bird_logic,
    build_early_birds_ladder,
    accrue_overtime_points,
)


async def handle_checkin(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    if message is None:
        return
    tg_user = update.effective_user
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    username = tg_user.username or f"user_{user_id}"

    db = await read_all()
    user = await get_user(db, user_id, username=username)
    if not user.get("active", False):
        await message.reply_text("⛔️ حساب شما توسط مدیریت فعال نشده است.")
        return

    ok, response, when = await record_check_in(db, user)
    if not ok:
        await message.reply_text(response)
        return

    got_yellow = await maybe_add_yellow(db, user, when)

    just_awarded = await handle_early_bird_logic(db, user_id)
    ladder_text = build_early_birds_ladder(db)

    await write_all(db)

    time_str = when.strftime("%H:%M")
    display = user.get("display_name") or username

    if got_yellow:
        await message.reply_text(
            f"⏰ دیر کردی! کارت زرد گرفتی.\nولی ورودت در ساعت {time_str} ثبت شد ✅"
        )
    else:
        await message.reply_text(f"✅ ورود امروز در ساعت {time_str} ثبت شد.")

    if just_awarded:
        await message.reply_text("🏅 شما بین چهار نفر اول امروز بودید؛ 1 امتیاز گرفتید!")

    await message.reply_text(ladder_text)

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


async def handle_checkout(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    if message is None:
        return
    tg_user = update.effective_user
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    username = tg_user.username or f"user_{user_id}"

    db = await read_all()
    user = await get_user(db, user_id, username=username)
    if not user.get("active", False):
        await message.reply_text("⛔️ حساب شما توسط مدیریت فعال نشده است.")
        return

    ok, response, when = await record_check_out(db, user)
    if not ok:
        await message.reply_text(response)
        return

    first_in = first_check_in_for_day(user, when.date())

    worked_str = ""
    overtime_minutes = 0
    overtime_points = 0
    overtime_remainder = 0
    if first_in:
        delta = when - first_in
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        worked_str = f" و امروز جمعاً {hours} ساعت و {minutes} دقیقه کار کرد"

        six_pm = when.replace(hour=18, minute=0, second=0, microsecond=0)
        if when > six_pm:
            overtime_delta = when - six_pm
            overtime_minutes = overtime_delta.seconds // 60
            if overtime_minutes > 0:
                overtime_points, overtime_remainder = accrue_overtime_points(user, overtime_minutes)

    time_str = when.strftime("%H:%M")
    display = user.get("display_name") or username

    lines = [f"📢 {display} در ساعت {time_str} خارج شد{worked_str}."]
    if overtime_minutes > 0:
        if overtime_points > 0:
            line = f"🏆 {overtime_minutes} دقیقه اضافه‌کاری امروز ثبت شد و {overtime_points} امتیاز گرفت."
            if overtime_remainder:
                line += f" باقی‌مانده تا امتیاز بعدی: {overtime_remainder} دقیقه."
        else:
            minutes_to_next = 60 - overtime_remainder if overtime_remainder else 60
            line = f"⏱️ {overtime_minutes} دقیقه اضافه‌کاری امروز ثبت شد. تا امتیاز بعدی {minutes_to_next} دقیقه باقی مانده است."
        lines.append(line)

    text = "\n".join(lines)

    await write_all(db)

    for uid in db:
        if uid == "_config":
            continue
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except Exception:
            pass


async def my_checkins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message is None:
        return
    tg_user = update.effective_user
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    db = await read_all()
    user = db.get(user_id)

    if not user or not user.get("check_ins"):
        await message.reply_text("هیچ ورودی ثبت نشده است.")
        return

    lines = ["📋 ورودهای شما:"]
    for rec in user.get("check_ins", [])[-10:]:  # show last 10
        lines.append(f"- {rec['datetime']}")
    await message.reply_text("\n".join(lines))


async def my_checkouts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message is None:
        return
    tg_user = update.effective_user
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    db = await read_all()
    user = db.get(user_id)

    if not user or not user.get("check_outs"):
        await message.reply_text("هیچ خروجی ثبت نشده است.")
        return

    lines = ["🏁 خروج‌های شما:"]
    for rec in user.get("check_outs", [])[-10:]:  # show last 10
        lines.append(f"- {rec['datetime']}")
    await message.reply_text("\n".join(lines))


async def my_yellow_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if message is None:
        return
    tg_user = update.effective_user
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    db = await read_all()
    user = db.get(user_id)

    if not user or not user.get("yellow_cards"):
        await message.reply_text("🎉 شما هیچ کارت زردی ندارید.")
        return

    lines = ["📒 کارت‌های زرد شما:"]
    for rec in user.get("yellow_cards", [])[-10:]:  # show last 10
        lines.append(f"- {rec}")
    await message.reply_text("\n".join(lines))
