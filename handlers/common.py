from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from ..storage import read_all, write_all, get_user
from ..config import MAIN_MENU



def _msg(update: Update):
    return update.effective_message


def start_callback_data(data: str | None) -> str | None:
    if not data:
        return None
    parts = data.split(":", 1)
    if len(parts) != 2:
        return None
    return parts[1]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = _msg(update)
    if message is None:
        return
    tg_user = update.effective_user
    if tg_user is None:
        return

    user_id = str(tg_user.id)
    username = tg_user.username
    first_name = getattr(tg_user, "first_name", None)

    db = await read_all()
    user = await get_user(db, user_id, username=username, first_name=first_name)
    await write_all(db)

    if not user.get("active", False):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 بررسی وضعیت من", callback_data=f"check_status:{user_id}")]
        ])
        return await message.reply_text(
            "👋 سلام! حساب شما ساخته شد ولی هنوز توسط مدیریت فعال نشده است.",
            reply_markup=keyboard
        )

    await message.reply_text(
        "بزن بریم آفیسر 🚀",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
    )


async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    user_id = start_callback_data(query.data)
    if not user_id:
        return

    db = await read_all()
    user = db.get(user_id)

    if not user:
        return await query.edit_message_text("❌ کاربر یافت نشد.")

    if not user.get("active", False):
        await query.edit_message_text("⛔️ هنوز حساب شما توسط مدیریت فعال نشده است.")
    else:
        await query.edit_message_text("✅ حساب شما فعال شد. بزن بریم آفیسر 🚀")
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="🎉 حالا می‌توانید از امکانات استفاده کنید.",
                reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
            )
        except Exception:
            pass
