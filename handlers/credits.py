from telegram import Update
from telegram.ext import ContextTypes

from ..config import ADMIN_IDS
from ..storage import read_all, write_all, get_user
from ..services.credits import POINT_VALUE, get_balance, request_withdrawal, update_balance


def _msg(update: Update):
    return update.effective_message


def _user(update: Update):
    return update.effective_user


def _query(update: Update):
    return update.callback_query


async def handle_withdraw_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approve/reject button clicks for withdrawals (admin only)."""
    query = _query(update)
    if query is None:
        return
    await query.answer()

    parts = (query.data or "").split(":", 2)
    if len(parts) != 3:
        return
    action, uid, index_str = parts
    try:
        index = int(index_str)
    except (TypeError, ValueError):
        return

    db = await read_all()
    user = await get_user(db, uid)
    wlist = user.get("withdrawals") or []

    if index < 0 or index >= len(wlist):
        return await query.edit_message_text("❗️ شماره درخواست نامعتبر است.")

    w = wlist[index]

    if action == "approve":
        w["status"] = "approved"
        await write_all(db)

        points_after = int(user.get("points", 0))
        await query.edit_message_text(f"✅ برداشت {w['amount']:,} تومان تایید شد.")
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=(
                    f"✅ برداشت {w['amount']:,} تومان برای شما تایید شد.\n"
                    f"امتیاز فعلی: {points_after} و موجودی: {points_after * POINT_VALUE:,} تومان"
                ),
            )
        except Exception:
            pass

    elif action == "reject":
        w["status"] = "rejected"
        points_used = w.get("points")
        if points_used is None:
            points_used = (w.get("amount", 0) or 0) // POINT_VALUE
        points_used = int(points_used or 0)
        if points_used > 0:
            user["points"] = int(user.get("points", 0)) + points_used
        update_balance(user)
        await write_all(db)

        await query.edit_message_text(f"❌ برداشت {w['amount']:,} تومان رد شد.")
        refund_text = f"❌ برداشت {w['amount']:,} تومان رد شد"
        if points_used:
            refund_text += f" و {points_used} امتیاز به حساب شما بازگشت."
        else:
            refund_text += "."
        try:
            await context.bot.send_message(chat_id=int(uid), text=refund_text)
        except Exception:
            pass

    else:
        return



async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    db = await read_all()
    user = await get_user(db, user_id, username=tg_user.username, first_name=tg_user.first_name)

    balance = get_balance(user)
    points = user.get("points", 0)

    text = (
        f"امتیاز فعلی: {points}\n"
        f"موجودی معادل: {balance:,} تومان"
    )
    await msg.reply_text(text)


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    db = await read_all()
    user = await get_user(db, user_id, username=tg_user.username, first_name=tg_user.first_name)

    args = context.args or []
    if not args:
        return await msg.reply_text("❗️ دستور صحیح: /withdraw <مبلغ>")

    try:
        amount = int(args[0])
    except ValueError:
        return await msg.reply_text("❗️ مبلغ باید عدد باشد.")

    try:
        w = request_withdrawal(user, amount)
    except ValueError as e:
        return await msg.reply_text(f"❌ {str(e)}")

    await write_all(db)

    await msg.reply_text(
        f"درخواست برداشت {w['amount']:,} تومان ثبت شد (وضعیت: {w['status']})."
    )


async def list_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if not args:
        return await msg.reply_text("❗️ استفاده: /list_withdraws <user_id>")

    target_id = args[0]
    db = await read_all()
    user = await get_user(db, target_id)

    wlist = user.get("withdrawals") or []
    if not wlist:
        return await msg.reply_text("❗️ هیچ درخواستی وجود ندارد.")

    lines = [
        f"درخواست‌های {user.get('display_name') or target_id}:"
    ]
    for i, w in enumerate(wlist, start=1):
        lines.append(f"{i}. {w['datetime']} → {w['amount']:,} تومان (وضعیت: {w['status']})")
    await msg.reply_text("\n".join(lines))


async def approve_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if len(args) < 2:
        return await msg.reply_text("❗️ استفاده: /approve_withdraw <user_id> <index>")

    target_id = args[0]
    try:
        index = int(args[1]) - 1
    except ValueError:
        return await msg.reply_text("❗️ شماره درخواست نامعتبر است.")

    db = await read_all()
    user = await get_user(db, target_id)
    wlist = user.get("withdrawals") or []

    if index < 0 or index >= len(wlist):
        return await msg.reply_text("❗️ شماره درخواست نامعتبر است.")

    wlist[index]["status"] = "approved"
    await write_all(db)

    await msg.reply_text("✅ برداشت تایید شد.")
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"✅ برداشت {wlist[index]['amount']:,} تومان برای شما تایید شد."
        )
    except Exception:
        pass


async def reject_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if len(args) < 2:
        return await msg.reply_text("❗️ استفاده: /reject_withdraw <user_id> <index>")

    target_id = args[0]
    try:
        index = int(args[1]) - 1
    except ValueError:
        return await msg.reply_text("❗️ شماره درخواست نامعتبر است.")

    db = await read_all()
    user = await get_user(db, target_id)
    wlist = user.get("withdrawals") or []

    if index < 0 or index >= len(wlist):
        return await msg.reply_text("❗️ شماره درخواست نامعتبر است.")

    withdrawal = wlist[index]
    amount = withdrawal.get("amount", 0)
    withdrawal["status"] = "rejected"

    points_used = withdrawal.get("points")
    if points_used is None:
        points_used = (amount or 0) // POINT_VALUE
    points_used = int(points_used or 0)
    if points_used > 0:
        user["points"] = int(user.get("points", 0)) + points_used
    update_balance(user)
    await write_all(db)

    await msg.reply_text("❌ برداشت رد شد و مبلغ به اعتبار بازگشت.")
    try:
        refund_text = f"❌ برداشت {amount:,} تومان رد شد"
        if points_used:
            refund_text += f" و {points_used} امتیاز به حساب شما بازگشت."
        else:
            refund_text += "."
        await context.bot.send_message(chat_id=int(target_id), text=refund_text)
    except Exception:
        pass



async def pending_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    db = await read_all()
    lines = ["درخواست‌های برداشت در انتظار تایید:"]

    found = False
    for uid, user in db.items():
        if uid == "_config":
            continue
        for i, w in enumerate(user.get("withdrawals", []), start=1):
            if w["status"] == "pending":
                found = True
                name = user.get("display_name") or user.get("username") or uid
                lines.append(f"{name} ({uid}) → {i}. {w['amount']:,} تومان در {w['datetime']}")

    if not found:
        return await msg.reply_text("✅ هیچ درخواست برداشتی در انتظار تایید نیست.")

    await msg.reply_text("\n".join(lines))


async def my_balance_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance when user clicks دُنگ موجودی."""
    await my_balance(update, context)


async def withdraw_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for amount when they click درخواست برداشت."""
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    context.user_data["awaiting_withdraw"] = True
    await msg.reply_text("لطفاً مبلغ برداشت را به تومان وارد کنید (مثلاً: 500000):")


async def handle_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_withdraw"):
        return

    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    db = await read_all()
    user = await get_user(db, user_id, username=tg_user.username, first_name=tg_user.first_name)

    try:
        amount = int((msg.text or "").strip())
    except ValueError:
        return await msg.reply_text("❗️ لطفاً یک عدد معتبر وارد کنید.")

    try:
        w = request_withdrawal(user, amount)
    except ValueError as e:
        return await msg.reply_text(f"❌ {str(e)}")

    await write_all(db)
    context.user_data["awaiting_withdraw"] = False

    await msg.reply_text(
        f"درخواست برداشت {w['amount']:,} تومان ثبت شد (وضعیت: {w['status']})."
    )
