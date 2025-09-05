# TODO: /task, MY TASKS, tasks done
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler
from ..storage import read_all, write_all, get_user

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    db = await read_all()
    user = await get_user(db, user_id)

    tasks = user.get("tasks", [])
    if not tasks:
        return await update.message.reply_text("🎉 شما هیچ مأموریت فعالی ندارید.")

    buttons = []
    for t in tasks:
        buttons.append([
            InlineKeyboardButton(f"✅ {t['text']}", callback_data=f"done:{t['id']}")
        ])

    await update.message.reply_text(
        "📝 ماموریت‌های شما:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def task_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    db = await read_all()
    user = await get_user(db, user_id)

    task_id = query.data.split(":")[1]
    tasks = user.get("tasks", [])
    done_list = user.setdefault("tasks_done", [])

    task = next((t for t in tasks if t["id"] == task_id), None)
    if task:
        tasks.remove(task)
        done_list.append(task)
        await write_all(db)
        await query.edit_message_text(f"✅ مأموریت انجام شد: {task['text']}")
    else:
        await query.edit_message_text("❌ این مأموریت دیگر وجود ندارد.")
