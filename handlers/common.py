from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from ..storage import read_all, write_all, get_user
from ..config import MAIN_MENU

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username

    db = await read_all()
    user = await get_user(db, user_id, username=username)
    await write_all(db)

    if not user.get("active", False):
        # Show inline button to check status
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 بررسی وضعیت من", callback_data=f"check_status:{user_id}")]
        ])
        return await update.message.reply_text(
            "👋 سلام! حساب شما ساخته شد ولی هنوز توسط مدیریت فعال نشده است.",
            reply_markup=keyboard
        )

    # If already active
    await update.message.reply_text(
        "بزن بریم آفیسر 🚀",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
    )


async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.data.split(":")[1]
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
