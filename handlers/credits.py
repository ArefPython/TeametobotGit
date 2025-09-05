from telegram import Update
from telegram.ext import ContextTypes
from ..storage import read_all, write_all, get_user
from ..services.credits import get_balance, request_withdrawal

async def handle_withdraw_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approve/reject button clicks for withdrawals (admin only)."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    action, uid, index = parts[0], parts[1], int(parts[2])

    db = await read_all()
    user = await get_user(db, uid)
    wlist = user.get("withdrawals", [])

    if index < 0 or index >= len(wlist):
        return await query.edit_message_text("❗️ درخواست نامعتبر است.")

    w = wlist[index]

    if action == "approve":
        w["status"] = "approved"
        await write_all(db)

        await query.edit_message_text(f"✅ برداشت {w['amount']:,} تومان تایید شد.")
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"✅ برداشت {w['amount']:,} تومان شما تایید شد.\n"
                     f"امتیاز فعلی: {user['points']} → اعتبار: {user['points'] * 100_000:,} تومان"
            )
        except Exception:
            pass

    elif action == "reject":
        w["status"] = "rejected"
        # 🔹 return points to user (since we deduct on request)
        user["points"] = int(user.get("points", 0)) + w.get("points", 0)
        update_balance(user)
        await write_all(db)

        await query.edit_message_text(f"❌ برداشت {w['amount']:,} تومان رد شد.")
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"❌ برداشت {w['amount']:,} تومان شما رد شد و {w.get('points', 0)} امتیاز به حساب بازگشت."
            )
        except Exception:
            pass

async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = await read_all()
    user = await get_user(db, user_id)

    balance = get_balance(user)
    points = user.get("points", 0)

    text = (
        f"⭐️ امتیاز شما: {points}\n"
        f"💰 اعتبار شما: {balance:,} تومان"
    )
    await update.message.reply_text(text)

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = await read_all()
    user = await get_user(db, user_id)

    if not context.args:
        return await update.message.reply_text("❗️ استفاده: /withdraw <مبلغ>")

    try:
        amount = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("❗️ مبلغ باید عدد باشد.")

    try:
        w = request_withdrawal(user, amount)
    except ValueError as e:
        return await update.message.reply_text(f"❌ {str(e)}")

    await write_all(db)

    await update.message.reply_text(
        f"📤 درخواست برداشت {w['amount']:,} تومان ثبت شد (وضعیت: {w['status']})"
    )

from ..config import ADMIN_IDS

async def list_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: list all withdrawal requests of a user."""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("⛔️ دسترسی ندارید.")
    if not context.args:
        return await update.message.reply_text("❗️ استفاده: /list_withdraws <user_id>")

    target_id = context.args[0]
    db = await read_all()
    user = await get_user(db, target_id)

    wlist = user.get("withdrawals", [])
    if not wlist:
        return await update.message.reply_text("❗️ هیچ درخواستی وجود ندارد.")

    lines = [f"💰 لیست درخواست‌های برداشت {user.get('display_name') or target_id}:"]
    for i, w in enumerate(wlist, start=1):
        lines.append(f"{i}. {w['datetime']} → {w['amount']:,} تومان (وضعیت: {w['status']})")
    await update.message.reply_text("\n".join(lines))


async def approve_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: approve a withdrawal request."""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("⛔️ دسترسی ندارید.")
    if len(context.args) < 2:
        return await update.message.reply_text("❗️ استفاده: /approve_withdraw <user_id> <index>")

    target_id = context.args[0]
    index = int(context.args[1]) - 1

    db = await read_all()
    user = await get_user(db, target_id)
    wlist = user.get("withdrawals", [])

    if index < 0 or index >= len(wlist):
        return await update.message.reply_text("❗️ شماره درخواست نامعتبر است.")

    wlist[index]["status"] = "approved"
    await write_all(db)

    await update.message.reply_text("✅ برداشت تایید شد.")
    try:
        await context.bot.send_message(chat_id=int(target_id),
                                       text=f"✅ برداشت {wlist[index]['amount']:,} تومان شما تایید شد.")
    except Exception:
        pass


async def reject_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: reject a withdrawal request and return money to balance."""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("⛔️ دسترسی ندارید.")
    if len(context.args) < 2:
        return await update.message.reply_text("❗️ استفاده: /reject_withdraw <user_id> <index>")

    target_id = context.args[0]
    index = int(context.args[1]) - 1

    db = await read_all()
    user = await get_user(db, target_id)
    wlist = user.get("withdrawals", [])

    if index < 0 or index >= len(wlist):
        return await update.message.reply_text("❗️ شماره درخواست نامعتبر است.")

    amount = wlist[index]["amount"]
    wlist[index]["status"] = "rejected"
    user["balance"] = int(user.get("balance", 0)) + amount
    await write_all(db)

    await update.message.reply_text("❌ برداشت رد شد و مبلغ به اعتبار بازگشت.")
    try:
        await context.bot.send_message(chat_id=int(target_id),
                                       text=f"❌ برداشت {amount:,} تومان شما رد شد و مبلغ به حساب بازگشت.")
    except Exception:
        pass

async def pending_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: list all pending withdrawal requests across all users."""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("⛔️ دسترسی ندارید.")

    db = await read_all()
    lines = ["💰 درخواست‌های برداشت در انتظار تایید:"]

    found = False
    for uid, user in db.items():
        if uid == "_config":
            continue
        for i, w in enumerate(user.get("withdrawals", []), start=1):
            if w["status"] == "pending":
                found = True
                name = user.get("display_name") or user.get("username") or uid
                lines.append(f"👤 {name} ({uid}) → {i}. {w['amount']:,} تومان در {w['datetime']}")

    if not found:
        return await update.message.reply_text("✅ هیچ درخواست برداشتی در انتظار تایید نیست.")

    await update.message.reply_text("\n".join(lines))

async def my_balance_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance when user clicks 💰 موجودی من"""
    await my_balance(update, context)


async def withdraw_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for amount when they click 📤 درخواست برداشت"""
    user_id = str(update.effective_user.id)
    context.user_data["awaiting_withdraw"] = True
    await update.message.reply_text("لطفاً مبلغ برداشت را به تومان وارد کنید (مثلاً: 500000):")

async def handle_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_withdraw"):
        return  # not in withdraw flow

    user_id = str(update.effective_user.id)
    db = await read_all()
    user = await get_user(db, user_id)

    try:
        amount = int(update.message.text.strip())
    except ValueError:
        return await update.message.reply_text("❗️ لطفاً یک عدد معتبر وارد کنید.")

    try:
        w = request_withdrawal(user, amount)
    except ValueError as e:
        return await update.message.reply_text(f"❌ {str(e)}")

    await write_all(db)
    context.user_data["awaiting_withdraw"] = False

    await update.message.reply_text(
        f"📤 درخواست برداشت {w['amount']:,} تومان ثبت شد (وضعیت: {w['status']})"
    )
