from __future__ import annotations

from typing import Any, MutableMapping, cast

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..config import ADMIN_IDS
from ..services.credits import POINT_VALUE, get_balance, request_withdrawal, update_balance
from ..storage import get_user, read_all, write_all


def _msg(update: Update):
    return update.effective_message


def _user(update: Update):
    return update.effective_user


def _query(update: Update):
    return update.callback_query


async def _require_admin(update: Update) -> bool:
    msg = _msg(update)
    tg_user = _user(update)
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        if msg is not None:
            await msg.reply_text("⛔️ You are not allowed to use this command.")
        return False
    return True


# Conversation states
(
    LIST_WITHDRAWS_USER,
    APPROVE_WITHDRAW_USER,
    APPROVE_WITHDRAW_INDEX,
    REJECT_WITHDRAW_USER,
    REJECT_WITHDRAW_INDEX,
) = range(5)

CREDITS_STATE_KEYS = {"credits_approve_target", "credits_reject_target"}


async def credits_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for key in CREDITS_STATE_KEYS:
        context.user_data.pop(key, None)
    msg = _msg(update)
    if msg is not None:
        await msg.reply_text("❎ Cancelled.")
    return ConversationHandler.END


async def handle_withdraw_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approve/reject callback buttons (admin only)."""
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
        await query.edit_message_text("❗️ Request number is invalid.")
        return

    entry = wlist[index]

    if action == "approve":
        entry["status"] = "approved"
        await write_all(db)
        points_after = int(user.get("points", 0))
        await query.edit_message_text(f"✅ Withdrawal {entry['amount']:,} approved.")
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=(
                    f"✅ Your withdrawal for {entry['amount']:,} was approved.\n"
                    f"Current points: {points_after} (≈ {points_after * POINT_VALUE:,} value)"
                ),
            )
        except Exception:
            pass
    elif action == "reject":
        entry["status"] = "rejected"
        points_used = entry.get("points")
        if points_used is None:
            points_used = (entry.get("amount", 0) or 0) // POINT_VALUE
        points_used = int(points_used or 0)
        if points_used > 0:
            user["points"] = int(user.get("points", 0)) + points_used
        update_balance(user)
        await write_all(db)

        await query.edit_message_text(f"❌ Withdrawal {entry['amount']:,} rejected.")
        refund_text = f"❌ Withdrawal {entry['amount']:,} rejected."
        if points_used:
            refund_text += f" {points_used} points returned to your balance."
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

    await msg.reply_text(
        f"ℹ️ Points: {points}\n"
        f"💰 Balance: {balance:,} (in Toman)"
    )


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
        await msg.reply_text("Usage: /withdraw <amount>")
        return

    try:
        amount = int(args[0])
    except ValueError:
        await msg.reply_text("Amount must be a number.")
        return

    try:
        record = request_withdrawal(user, amount)
    except ValueError as exc:
        await msg.reply_text(f"❌ {exc}")
        return

    await write_all(db)
    await msg.reply_text(
        f"✅ Withdrawal request for {record['amount']:,} submitted (status: {record['status']})."
    )


async def list_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if args:
        return await _send_withdraw_list(update, context, args[0])

    await msg.reply_text("Send the user ID (or /cancel).")
    return LIST_WITHDRAWS_USER


async def list_withdraws_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END

    target_id = (msg.text or "").strip()
    if not target_id:
        await msg.reply_text("User ID cannot be empty. Send again or /cancel.")
        return LIST_WITHDRAWS_USER

    return await _send_withdraw_list(update, context, target_id)


async def _send_withdraw_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: str
):
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END

    db = await read_all()
    user = await get_user(db, target_id)

    requests = user.get("withdrawals") or []
    if not requests:
        await msg.reply_text("No withdrawal requests found.")
        return ConversationHandler.END

    lines = [f"📄 Withdrawals for {user.get('display_name') or target_id}:"]
    for idx, record in enumerate(requests, start=1):
        lines.append(
            f"{idx}. {record['datetime']} — {record['amount']:,} (status: {record['status']})"
        )
    await msg.reply_text("\n".join(lines))
    return ConversationHandler.END


async def approve_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if len(args) >= 2:
        return await _apply_approve_withdraw(update, context, args[0], args[1])

    await msg.reply_text("Send the user ID (or /cancel).")
    return APPROVE_WITHDRAW_USER


async def approve_withdraw_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END

    target_id = (msg.text or "").strip()
    if not target_id:
        await msg.reply_text("User ID cannot be empty. Send again or /cancel.")
        return APPROVE_WITHDRAW_USER

    context.user_data["credits_approve_target"] = target_id
    await msg.reply_text("Send the request number (or /cancel).")
    return APPROVE_WITHDRAW_INDEX


async def approve_withdraw_index(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END

    index_str = (msg.text or "").strip()
    target_id = context.user_data.pop("credits_approve_target", None)
    if not target_id:
        await msg.reply_text("User ID missing. Please run /approve_withdraw again.")
        return ConversationHandler.END

    return await _apply_approve_withdraw(update, context, target_id, index_str)


async def _apply_approve_withdraw(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: str, index_str: str
):
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END
    try:
        index = int(index_str) - 1
    except ValueError:
        await msg.reply_text("❗️ Request number is invalid.")
        return ConversationHandler.END

    db = await read_all()
    user = await get_user(db, target_id)
    records = user.get("withdrawals") or []

    if index < 0 or index >= len(records):
        await msg.reply_text("❗️ Request number is invalid.")
        return ConversationHandler.END

    records[index]["status"] = "approved"
    await write_all(db)

    await msg.reply_text("✅ Withdrawal approved.")
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"✅ Withdrawal {records[index]['amount']:,} confirmed for you.",
        )
    except Exception:
        pass
    return ConversationHandler.END


async def reject_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if len(args) >= 2:
        return await _apply_reject_withdraw(update, context, args[0], args[1])

    await msg.reply_text("Send the user ID (or /cancel).")
    return REJECT_WITHDRAW_USER


async def reject_withdraw_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END

    target_id = (msg.text or "").strip()
    if not target_id:
        await msg.reply_text("User ID cannot be empty. Send again or /cancel.")
        return REJECT_WITHDRAW_USER

    context.user_data["credits_reject_target"] = target_id
    await msg.reply_text("Send the request number (or /cancel).")
    return REJECT_WITHDRAW_INDEX


async def reject_withdraw_index(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END

    index_str = (msg.text or "").strip()
    target_id = context.user_data.pop("credits_reject_target", None)
    if not target_id:
        await msg.reply_text("User ID missing. Please run /reject_withdraw again.")
        return ConversationHandler.END

    return await _apply_reject_withdraw(update, context, target_id, index_str)


async def _apply_reject_withdraw(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: str, index_str: str
):
    msg = _msg(update)
    if msg is None:
        return ConversationHandler.END

    try:
        index = int(index_str) - 1
    except ValueError:
        await msg.reply_text("❗️ Request number is invalid.")
        return ConversationHandler.END

    db = await read_all()
    user = await get_user(db, target_id)
    records = user.get("withdrawals") or []

    if index < 0 or index >= len(records):
        await msg.reply_text("❗️ Request number is invalid.")
        return ConversationHandler.END

    entry = records[index]
    amount = entry.get("amount", 0)
    entry["status"] = "rejected"

    points_used = entry.get("points")
    if points_used is None:
        points_used = (amount or 0) // POINT_VALUE
    points_used = int(points_used or 0)
    if points_used > 0:
        user["points"] = int(user.get("points", 0)) + points_used
    update_balance(user)
    await write_all(db)

    await msg.reply_text("❌ Withdrawal rejected and refunded to balance.")
    try:
        notification = f"❌ Withdrawal {amount:,} rejected."
        if points_used:
            notification += f" {points_used} points returned."
        else:
            notification += ""
        await context.bot.send_message(chat_id=int(target_id), text=notification)
    except Exception:
        pass

    return ConversationHandler.END


async def pending_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    if not await _require_admin(update):
        return

    db = await read_all()
    lines = ["⏳ Pending withdrawal requests:"]
    found = False
    for uid, user in db.items():
        if uid == "_config":
            continue
        for idx, record in enumerate(user.get("withdrawals", []), start=1):
            if record.get("status") == "pending":
                found = True
                name = user.get("display_name") or user.get("username") or uid
                lines.append(
                    f"{name} ({uid}) — #{idx}: {record['amount']:,} at {record['datetime']}"
                )
    if not found:
        await msg.reply_text("No pending requests 🎉")
        return

    await msg.reply_text("\n".join(lines))


async def my_balance_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await my_balance(update, context)


async def withdraw_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None:
        return

    user_data = cast(MutableMapping[str, Any], context.user_data)
    user_data["awaiting_withdraw"] = True
    await msg.reply_text("Please enter the withdrawal amount (e.g. 500000).")


async def handle_withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = cast(MutableMapping[str, Any], context.user_data)
    if not user_data.get("awaiting_withdraw"):
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
        await msg.reply_text("Amount must be a number. Try again.")
        return

    try:
        record = request_withdrawal(user, amount)
    except ValueError as exc:
        await msg.reply_text(f"❌ {exc}")
        return

    await write_all(db)
    user_data["awaiting_withdraw"] = False
    await msg.reply_text(
        f"✅ Withdrawal request {record['amount']:,} submitted (status: {record['status']})."
    )


CREDITS_CONVERSATIONS = [
    ConversationHandler(
        entry_points=[CommandHandler("list_withdraws", list_withdraws)],
        states={
            LIST_WITHDRAWS_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, list_withdraws_user)],
        },
        fallbacks=[CommandHandler("cancel", credits_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("approve_withdraw", approve_withdraw)],
        states={
            APPROVE_WITHDRAW_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, approve_withdraw_user)],
            APPROVE_WITHDRAW_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, approve_withdraw_index)],
        },
        fallbacks=[CommandHandler("cancel", credits_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("reject_withdraw", reject_withdraw)],
        states={
            REJECT_WITHDRAW_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_withdraw_user)],
            REJECT_WITHDRAW_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, reject_withdraw_index)],
        },
        fallbacks=[CommandHandler("cancel", credits_cancel)],
        allow_reentry=True,
    ),
]

