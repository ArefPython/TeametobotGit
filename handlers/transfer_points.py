from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..config import BTN_TRANSFER
from ..services.credits import update_balance
from ..storage import read_all, write_all, get_user

SELECT_RECIPIENT, SELECT_AMOUNT, CONFIRM_TRANSFER = range(3)


def _msg(update: Update):
    return update.effective_message


def _user(update: Update):
    return update.effective_user


def _query(update: Update):
    return update.callback_query


async def start_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point of the transfer conversation."""
    prompt = "لطفاً نام کاربری گیرنده را وارد کنید:"
    message = _msg(update)
    if message is not None:
        await message.reply_text(prompt)
    else:
        query = _query(update)
        if query and query.message:
            await query.message.reply_text(prompt)
    return SELECT_RECIPIENT


async def input_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the input of the recipient's username."""
    message = _msg(update)
    if message is None or not message.text:
        return SELECT_RECIPIENT

    username_input = message.text.strip()
    if username_input.startswith("@"):
        username_input = username_input[1:]

    db = await read_all()
    target_id = None
    target_user_data = None
    for uid, user_data in db.items():
        if uid == "_config":
            continue
        current_username = (user_data.get("username") or "").lower()
        if current_username and current_username == username_input.lower():
            target_id = uid
            target_user_data = user_data
            break

    if not target_id:
        await message.reply_text(
            "❌ کاربری با این نام پیدا نشد. نام دیگری وارد کنید یا /cancel را بفرستید."
        )
        return SELECT_RECIPIENT

    tg_user = _user(update)
    if tg_user and str(tg_user.id) == str(target_id):
        await message.reply_text(
            "❗️ نمی‌توانید امتیاز را به خودتان انتقال دهید. نام کاربری دیگری وارد کنید یا /cancel را بفرستید."
        )
        return SELECT_RECIPIENT

    context.user_data["transfer_target_id"] = target_id
    context.user_data["transfer_target_username"] = target_user_data.get("username") or target_id

    await message.reply_text("لطفاً تعداد امتیاز مورد نظر برای انتقال را وارد کنید:")
    return SELECT_AMOUNT


async def input_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the input of the transfer amount."""
    message = _msg(update)
    if message is None or not message.text:
        return SELECT_AMOUNT

    text = message.text.strip()
    try:
        amount = int(text)
    except ValueError:
        await message.reply_text("❗️ لطفاً یک عدد معتبر وارد کنید.")
        return SELECT_AMOUNT

    if amount <= 0:
        await message.reply_text("❗️ مقدار باید عددی مثبت باشد.")
        return SELECT_AMOUNT

    tg_user = _user(update)
    if tg_user is None:
        return SELECT_AMOUNT

    db = await read_all()
    source_id = str(tg_user.id)
    source_user = await get_user(db, source_id, username=tg_user.username, first_name=tg_user.first_name)

    source_points = int(source_user.get("points", 0))
    if amount > source_points:
        await message.reply_text(f"❌ امتیاز کافی ندارید. امتیاز فعلی شما: {source_points}")
        return SELECT_AMOUNT

    context.user_data["transfer_amount"] = amount
    target_username = context.user_data.get("transfer_target_username", "کاربر")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید انتقال", callback_data="transfer_confirm"),
            InlineKeyboardButton("❌ انصراف", callback_data="transfer_cancel"),
        ]
    ])

    await message.reply_text(
        f"آیا {amount} امتیاز به {target_username} انتقال داده شود؟",
        reply_markup=keyboard,
    )
    return CONFIRM_TRANSFER


async def confirm_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = _query(update)
    if query is None:
        return ConversationHandler.END
    await query.answer()

    choice = query.data or ""
    if choice == "transfer_confirm":
        source_id = str(query.from_user.id)
        target_id = context.user_data.get("transfer_target_id")
        amount = context.user_data.get("transfer_amount")
        if not target_id or amount is None:
            await query.edit_message_text("❌ اطلاعات انتقال یافت نشد.")
            return ConversationHandler.END

        db = await read_all()
        source_user = await get_user(db, source_id)
        target_user = await get_user(db, target_id)

        if amount > int(source_user.get("points", 0)):
            await query.edit_message_text("❌ انتقال انجام نشد؛ امتیاز کافی ندارید.")
            return ConversationHandler.END

        source_user["points"] = int(source_user.get("points", 0)) - amount
        target_user["points"] = int(target_user.get("points", 0)) + amount
        update_balance(source_user)
        update_balance(target_user)
        await write_all(db)

        target_username = context.user_data.get("transfer_target_username", target_id)
        await query.edit_message_text(f"✅ {amount} امتیاز به {target_username} انتقال داده شد.")

        try:
            sender_name = query.from_user.username or query.from_user.first_name or "یک کاربر"
            await context.bot.send_message(
                chat_id=int(target_id),
                text=f"🎉 {amount} امتیاز از {sender_name} دریافت کردید."
            )
        except Exception:
            pass
    else:
        await query.edit_message_text("انتقال لغو شد.")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = _msg(update)
    if message is not None:
        await message.reply_text("انتقال لغو شد.")
    context.user_data.pop("transfer_target_id", None)
    context.user_data.pop("transfer_target_username", None)
    context.user_data.pop("transfer_amount", None)
    return ConversationHandler.END


transfer_points_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_TRANSFER}$"), start_transfer)],
    states={
        SELECT_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_recipient)],
        SELECT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_amount)],
        CONFIRM_TRANSFER: [CallbackQueryHandler(confirm_transfer, pattern="^transfer_confirm$|^transfer_cancel$")],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        MessageHandler(filters.Regex("(?i)^cancel$"), cancel),
    ],
)
