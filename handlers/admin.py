from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..config import ADMIN_IDS
from ..storage import read_all, write_all, ensure_config, get_user

# Conversation state constants
(
    NOTIFY_MESSAGE,
    SETNAME_USER,
    SETNAME_NAME,
    REMOVE_YELLOW_USER,
    REMOVE_YELLOW_INDEX,
    GIVE_YELLOW_USER,
    GIVE_YELLOW_REASON,
    ASSIGN_TASK_USER,
    ASSIGN_TASK_TEXT,
    ACTIVATE_USER_ID,
    DEACTIVATE_USER_ID,
    REMOVE_USER_ID,
) = range(12)

USER_DATA_KEYS = {
    "setname_target",
    "remove_yellow_target",
    "give_yellow_target",
    "assign_task_target",
}


def _msg(update: Update):
    return update.effective_message


async def _require_admin(update: Update) -> bool:
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        message = _msg(update)
        if message is not None:
            await message.reply_text("⛔️ You are not allowed to use this command.")
        return False
    return True


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for key in USER_DATA_KEYS:
        context.user_data.pop(key, None)
    message = _msg(update)
    if message is not None:
        await message.reply_text("❎ Cancelled.")
    return ConversationHandler.END


async def unlimit_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return
    if not await _require_admin(update):
        return

    db = await read_all()
    cfg = await ensure_config(db)
    today = date.today().isoformat()
    if today not in cfg["unlimited_dates"]:
        cfg["unlimited_dates"].append(today)
        await write_all(db)
    await message.reply_text("✅ Today is now unlimited.")


async def _broadcast_notification(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    db = await read_all()
    count = 0
    for uid in db:
        if uid == "_config":
            continue
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"📢 {text}")
            count += 1
        except Exception:
            pass

    await message.reply_text(f"✅ Notification sent to {count} users.")
    return ConversationHandler.END


async def notify_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if args:
        text = " ".join(args).strip()
        if text:
            return await _broadcast_notification(update, context, text)
        await message.reply_text("Message cannot be empty. Try again.")
        return ConversationHandler.END

    await message.reply_text("Please send the announcement text (or /cancel).")
    return NOTIFY_MESSAGE


async def notify_all_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    text = (message.text or "").strip()
    if not text:
        await message.reply_text("Message cannot be empty. Please send again or /cancel.")
        return NOTIFY_MESSAGE

    return await _broadcast_notification(update, context, text)


async def _apply_set_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: str, new_name: str
):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    db = await read_all()
    user = await get_user(db, target_id)

    old_name = user.get("display_name") or user.get("username") or target_id
    user["display_name"] = new_name
    await write_all(db)

    await message.reply_text(
        f"✅ Display name updated:\n{old_name} → {new_name}"
    )

    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"ℹ️ Your display name was updated to:\n{new_name}",
        )
    except Exception:
        pass

    return ConversationHandler.END


async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if len(args) >= 2:
        target_id = args[0]
        new_name = " ".join(args[1:]).strip()
        if new_name:
            return await _apply_set_name(update, context, target_id, new_name)
        await message.reply_text("Display name cannot be empty.")
        return ConversationHandler.END

    await message.reply_text("Send the user ID to rename (or /cancel).")
    return SETNAME_USER


async def set_name_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    target_id = (message.text or "").strip()
    if not target_id:
        await message.reply_text("User ID cannot be empty. Send again or /cancel.")
        return SETNAME_USER

    context.user_data["setname_target"] = target_id
    await message.reply_text("Send the new display name (or /cancel).")
    return SETNAME_NAME


async def set_name_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        context.user_data.pop("setname_target", None)
        return ConversationHandler.END

    new_name = (message.text or "").strip()
    if not new_name:
        await message.reply_text("Display name cannot be empty. Send again or /cancel.")
        return SETNAME_NAME

    target_id = context.user_data.pop("setname_target", None)
    if not target_id:
        await message.reply_text("User ID missing. Please run /setname again.")
        return ConversationHandler.END

    return await _apply_set_name(update, context, target_id, new_name)


async def _apply_remove_yellow(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: str, index_str: str
):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    try:
        index = int(index_str) - 1
    except ValueError:
        await message.reply_text("Invalid card number. Use digits only.")
        return ConversationHandler.END

    db = await read_all()
    user = await get_user(db, target_id)

    cards = user.get("yellow_cards", [])
    if not cards:
        await message.reply_text("The user has no yellow cards.")
        return ConversationHandler.END
    if index < 0 or index >= len(cards):
        await message.reply_text("Card number is out of range.")
        return ConversationHandler.END

    removed = cards.pop(index)
    await write_all(db)

    display = user.get("display_name") or user.get("username") or target_id
    await message.reply_text(f"✅ Removed card #{index + 1} from {display}.")

    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"ℹ️ A yellow card was removed:\n{removed}",
        )
    except Exception:
        pass

    return ConversationHandler.END


async def remove_yellow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if len(args) >= 2:
        return await _apply_remove_yellow(update, context, args[0], args[1])

    await message.reply_text("Send the user ID (or /cancel).")
    return REMOVE_YELLOW_USER


async def remove_yellow_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    target_id = (message.text or "").strip()
    if not target_id:
        await message.reply_text("User ID cannot be empty. Send again or /cancel.")
        return REMOVE_YELLOW_USER

    context.user_data["remove_yellow_target"] = target_id
    await message.reply_text("Send the card number to remove (or /cancel).")
    return REMOVE_YELLOW_INDEX


async def remove_yellow_index(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        context.user_data.pop("remove_yellow_target", None)
        return ConversationHandler.END

    index_str = (message.text or "").strip()
    target_id = context.user_data.pop("remove_yellow_target", None)
    if not target_id:
        await message.reply_text("User ID missing. Please run /remove_yellow again.")
        return ConversationHandler.END

    return await _apply_remove_yellow(update, context, target_id, index_str)


async def _apply_give_yellow(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: str, reason: str
):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    db = await read_all()
    user = await get_user(db, target_id)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"Manual yellow card at {now}: {reason}"
    user.setdefault("yellow_cards", []).append(entry)

    await write_all(db)

    display = user.get("display_name") or user.get("username") or target_id
    await message.reply_text(f"⚠️ Yellow card recorded for {display}.")

    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"⚠️ A yellow card was issued: {reason}",
        )
    except Exception:
        pass

    for uid, payload in (await read_all()).items():
        if uid == "_config":
            continue
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"⚠️ {display} received a yellow card ({reason}).",
            )
        except Exception:
            pass

    return ConversationHandler.END


async def give_yellow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if len(args) >= 2:
        return await _apply_give_yellow(update, context, args[0], " ".join(args[1:]))

    await message.reply_text("Send the user ID (or /cancel).")
    return GIVE_YELLOW_USER


async def give_yellow_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    target_id = (message.text or "").strip()
    if not target_id:
        await message.reply_text("User ID cannot be empty. Send again or /cancel.")
        return GIVE_YELLOW_USER

    context.user_data["give_yellow_target"] = target_id
    await message.reply_text("Send the reason (or /cancel).")
    return GIVE_YELLOW_REASON


async def give_yellow_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        context.user_data.pop("give_yellow_target", None)
        return ConversationHandler.END

    reason = (message.text or "").strip()
    if not reason:
        await message.reply_text("Reason cannot be empty. Send again or /cancel.")
        return GIVE_YELLOW_REASON

    target_id = context.user_data.pop("give_yellow_target", None)
    if not target_id:
        await message.reply_text("User ID missing. Please run /yellow again.")
        return ConversationHandler.END

    return await _apply_give_yellow(update, context, target_id, reason)


async def _apply_assign_task(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: str, task_text: str
):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    task_id = str(uuid4())[:8]

    db = await read_all()
    user = await get_user(db, target_id)
    user.setdefault("tasks", []).append({"id": task_id, "text": task_text})
    await write_all(db)

    display = user.get("display_name") or user.get("username") or target_id
    await message.reply_text(f"✅ Task assigned to {display}.")

    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"📝 New task:\n{task_text}\n(View it via MY TASKS button.)",
        )
    except Exception:
        pass

    return ConversationHandler.END


async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if len(args) >= 2:
        target_id = args[0]
        task_text = " ".join(args[1:]).strip()
        if task_text:
            return await _apply_assign_task(update, context, target_id, task_text)
        await message.reply_text("Task text cannot be empty.")
        return ConversationHandler.END

    await message.reply_text("Send the user ID (or /cancel).")
    return ASSIGN_TASK_USER


async def assign_task_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    target_id = (message.text or "").strip()
    if not target_id:
        await message.reply_text("User ID cannot be empty. Send again or /cancel.")
        return ASSIGN_TASK_USER

    context.user_data["assign_task_target"] = target_id
    await message.reply_text("Send the task text (or /cancel).")
    return ASSIGN_TASK_TEXT


async def assign_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        context.user_data.pop("assign_task_target", None)
        return ConversationHandler.END

    task_text = (message.text or "").strip()
    if not task_text:
        await message.reply_text("Task text cannot be empty. Send again or /cancel.")
        return ASSIGN_TASK_TEXT

    target_id = context.user_data.pop("assign_task_target", None)
    if not target_id:
        await message.reply_text("User ID missing. Please run /task again.")
        return ConversationHandler.END

    return await _apply_assign_task(update, context, target_id, task_text)


async def _set_active_flag(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target_id: str,
    *,
    active: bool,
):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    db = await read_all()
    user = db.get(target_id)
    if not user:
        await message.reply_text("User not found.")
        return ConversationHandler.END

    user["active"] = active
    await write_all(db)

    status = "activated" if active else "deactivated"
    await message.reply_text(f"✅ User {target_id} {status}.")

    if active:
        notify = (
            "✅ Your account has been activated. Welcome back! "
            "Please use the menu to continue."
        )
    else:
        notify = "⚠️ Your account has been deactivated."

    try:
        await context.bot.send_message(chat_id=int(target_id), text=notify)
    except Exception:
        pass

    return ConversationHandler.END


async def activate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if args:
        return await _set_active_flag(update, context, args[0], active=True)

    await message.reply_text("Send the user ID to activate (or /cancel).")
    return ACTIVATE_USER_ID


async def activate_user_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    target_id = (message.text or "").strip()
    if not target_id:
        await message.reply_text("User ID cannot be empty. Send again or /cancel.")
        return ACTIVATE_USER_ID
    return await _set_active_flag(update, context, target_id, active=True)


async def deactivate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if args:
        return await _set_active_flag(update, context, args[0], active=False)

    await message.reply_text("Send the user ID to deactivate (or /cancel).")
    return DEACTIVATE_USER_ID


async def deactivate_user_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    target_id = (message.text or "").strip()
    if not target_id:
        await message.reply_text("User ID cannot be empty. Send again or /cancel.")
        return DEACTIVATE_USER_ID
    return await _set_active_flag(update, context, target_id, active=False)


async def _apply_remove_user(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: str
):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    db = await read_all()
    if target_id not in db or target_id == "_config":
        await message.reply_text("User not found.")
        return ConversationHandler.END

    del db[target_id]
    await write_all(db)

    await message.reply_text(f"🗑️ User {target_id} removed.")

    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text="⚠️ Your data was removed from the system.",
        )
    except Exception:
        pass

    return ConversationHandler.END


async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END
    if not await _require_admin(update):
        return ConversationHandler.END

    args = context.args or []
    if args:
        return await _apply_remove_user(update, context, args[0])

    await message.reply_text("Send the user ID to remove (or /cancel).")
    return REMOVE_USER_ID


async def remove_user_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return ConversationHandler.END

    target_id = (message.text or "").strip()
    if not target_id:
        await message.reply_text("User ID cannot be empty. Send again or /cancel.")
        return REMOVE_USER_ID

    return await _apply_remove_user(update, context, target_id)


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return
    if not await _require_admin(update):
        return

    db = await read_all()
    lines = ["👥 Registered users:"]
    for uid, user in db.items():
        if uid == "_config":
            continue
        uname = user.get("username") or "-"
        dname = user.get("display_name") or "-"
        status = "✅ active" if user.get("active", False) else "🚫 inactive"
        lines.append(f"{uid} — @{uname} / {dname} ({status})")

    if len(lines) == 1:
        await message.reply_text("No users found.")
        return

    await message.reply_text("\n".join(lines))


async def list_inactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return
    if not await _require_admin(update):
        return

    db = await read_all()
    lines = ["🚫 Inactive users:"]
    for uid, user in db.items():
        if uid == "_config":
            continue
        if user.get("active", False):
            continue
        name = user.get("display_name") or user.get("username") or uid
        lines.append(f"{uid} — {name}")

    if len(lines) == 1:
        await message.reply_text("No inactive users 🎉")
        return

    await message.reply_text("\n".join(lines))


ADMIN_CONVERSATIONS = [
    ConversationHandler(
        entry_points=[CommandHandler("notify", notify_all)],
        states={
            NOTIFY_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, notify_all_message)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("setname", set_name)],
        states={
            SETNAME_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name_user)],
            SETNAME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_name_name)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("remove_yellow", remove_yellow)],
        states={
            REMOVE_YELLOW_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_yellow_user)],
            REMOVE_YELLOW_INDEX: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_yellow_index)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("yellow", give_yellow)],
        states={
            GIVE_YELLOW_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, give_yellow_user)],
            GIVE_YELLOW_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, give_yellow_reason)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("task", assign_task)],
        states={
            ASSIGN_TASK_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, assign_task_user)],
            ASSIGN_TASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, assign_task_text)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("activate", activate_user)],
        states={
            ACTIVATE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, activate_user_receive_id)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("deactivate", deactivate_user)],
        states={
            DEACTIVATE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, deactivate_user_receive_id)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    ),
    ConversationHandler(
        entry_points=[CommandHandler("remove_user", remove_user)],
        states={
            REMOVE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_user_receive_id)],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
        allow_reentry=True,
    ),
]

