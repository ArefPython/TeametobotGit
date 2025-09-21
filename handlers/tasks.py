from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler

from ..storage import read_all, write_all, get_user


def _msg(update: Update):
    return update.effective_message


def _user(update: Update):
    return update.effective_user


def _query(update: Update):
    return update.callback_query


async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = _user(update)
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    db = await read_all()
    user = await get_user(db, user_id, username=tg_user.username, first_name=tg_user.first_name)

    tasks = user.get("tasks") or []
    if not tasks:
        return await msg.reply_text("🎉 شما هیچ مأموریت فعالی ندارید.")

    buttons = [
        [InlineKeyboardButton(f"✅ {t['text']}", callback_data=f"done:{t['id']}")]
        for t in tasks
    ]

    await msg.reply_text(
        "📋 مأموریت‌های فعلی شما:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def task_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = _query(update)
    if query is None:
        return
    await query.answer()

    user_id = str(query.from_user.id)
    db = await read_all()
    user = await get_user(db, user_id)

    data = query.data or ""
    parts = data.split(":", 1)
    if len(parts) != 2:
        return
    task_id = parts[1]

    tasks = user.get("tasks") or []
    done_list = user.setdefault("tasks_done", [])

    task = next((t for t in tasks if t["id"] == task_id), None)
    if task:
        tasks.remove(task)
        done_list.append(task)
        await write_all(db)
        await query.edit_message_text(f"✅ مأموریت انجام شد: {task['text']}")
    else:
        await query.edit_message_text("❗️ مأموریت یافت نشد یا قبلاً انجام شده است.")
