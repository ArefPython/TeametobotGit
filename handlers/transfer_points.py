from ..config import BTN_TRANSFER
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from ..storage import read_all, write_all, get_user
from ..services.credits import update_balance

# Conversation state definitions
SELECT_RECIPIENT, SELECT_AMOUNT, CONFIRM_TRANSFER = range(3)

async def start_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point of the transfer conversation. Prompts for the recipient username."""
    if update.message:
        await update.message.reply_text("لطفاً نام کاربری گیرنده را وارد کنید:")  # "Please enter the recipient's username:"
    elif update.callback_query:
        await update.callback_query.message.reply_text("لطفاً نام کاربری گیرنده را وارد کنید:")  # "Please enter the recipient's username:"
    return SELECT_RECIPIENT

async def input_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the input of the recipient's username."""
    username_input = update.message.text.strip()
    if username_input.startswith("@"):
        username_input = username_input[1:]  # strip leading @ if provided
    # Load the current database of users
    db = await read_all()
    # Find a user with matching username (case-insensitive)
    target_id = None
    target_user_data = None
    for uid, user_data in db.items():
        if uid == "_config":
            continue  # skip config section in DB
        if user_data.get("username", "").lower() == username_input.lower():
            target_id = uid
            target_user_data = user_data
            break
    if not target_id:
        # No user found with that username
        await update.message.reply_text(
            "❌ کاربر یافت نشد. لطفاً یک نام کاربری معتبر وارد کنید یا /cancel را ارسال کنید."
        )  # "User not found. Enter a valid username or send /cancel to abort."
        return SELECT_RECIPIENT  # remain in this state to ask again
    if str(update.effective_user.id) == str(target_id):
        # User is trying to transfer to themselves – not allowed
        await update.message.reply_text(
            "❌ نمی‌توانید به خودتان امتیاز منتقل کنید. لطفاً نام کاربری دیگری را وارد کنید یا /cancel را ارسال کنید."
        )  # "You cannot transfer points to yourself. Enter another username or /cancel to cancel."
        return SELECT_RECIPIENT
    # Valid recipient found: store target info for later steps
    context.user_data["transfer_target_id"] = target_id
    context.user_data["transfer_target_username"] = target_user_data.get("username") or target_id
    # Ask for the amount of points to transfer
    await update.message.reply_text("لطفاً تعداد امتیازی که می‌خواهید انتقال دهید را وارد کنید:")  
    # "Please enter the number of points you want to transfer:"
    return SELECT_AMOUNT

async def input_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the input of the transfer amount."""
    text = update.message.text.strip()
    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text("❗️ لطفاً یک عدد معتبر وارد کنید.")  # "Please enter a valid number."
        return SELECT_AMOUNT  # ask for amount again
    if amount <= 0:
        await update.message.reply_text("❗️ مقدار باید یک عدد مثبت باشد.")  # "The amount must be a positive number."
        return SELECT_AMOUNT
    # Load user data to check balance
    db = await read_all()
    source_id = str(update.effective_user.id)
    source_user = await get_user(db, source_id)
    source_points = int(source_user.get("points", 0))
    if amount > source_points:
        # Not enough points to transfer
        await update.message.reply_text(
            f"❌ امتیاز کافی ندارید. امتیازات فعلی شما: {source_points}"
        )  # "Insufficient points. Your current points: X"
        return SELECT_AMOUNT
    # Store the amount and proceed to confirmation step
    context.user_data["transfer_amount"] = amount
    target_username = context.user_data.get("transfer_target_username", "کاربر مقصد")
    # Prepare inline buttons for confirmation
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید", callback_data="transfer_confirm"),
         InlineKeyboardButton("❌ لغو", callback_data="transfer_cancel")]
    ])
    await update.message.reply_text(
        f"انتقال {amount} امتیاز به {target_username} انجام شود؟",  # "Transfer X points to Y?" 
        reply_markup=keyboard
    )
    return CONFIRM_TRANSFER

async def confirm_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the inline confirmation or cancellation of the transfer."""
    query = update.callback_query
    await query.answer()  # acknowledge the callback
    if query.data == "transfer_confirm":
        # User confirmed the transfer – perform the transfer logic
        source_id = str(query.from_user.id)
        target_id = context.user_data.get("transfer_target_id")
        amount = context.user_data.get("transfer_amount")
        if not target_id or amount is None:
            # Missing data (shouldn't happen normally)
            await query.edit_message_text("❌ اطلاعات انتقال یافت نشد.")  # "Transfer information not found."
            return ConversationHandler.END
        # Load DB and get up-to-date user records
        db = await read_all()
        source_user = await get_user(db, source_id)
        target_user = await get_user(db, target_id)
        # Double-check source still has enough points
        if amount > int(source_user.get("points", 0)):
            await query.edit_message_text("❌ انتقال شکست خورد: امتیاز کافی نیست.")  # "Transfer failed: insufficient points."
            return ConversationHandler.END
        # Deduct points from source and add to target
        source_user["points"] = int(source_user.get("points", 0)) - amount
        target_user["points"] = int(target_user.get("points", 0)) + amount
        # Update balances (recalculate currency balance if used in the system)
        update_balance(source_user)
        update_balance(target_user)
        await write_all(db)  # persist changes to the JSON database
        # Confirm to the sender
        await query.edit_message_text(
            f"✅ {amount} امتیاز به {context.user_data.get('transfer_target_username')} منتقل شد."
        )  # "✅ X points have been transferred to Username."
        # Notify the recipient in their chat (if possible)
        try:
            sender_name = query.from_user.username or query.from_user.first_name or "یک کاربر"
            await context.bot.send_message(
                chat_id=int(target_id),
                text=f"💰 شما {amount} امتیاز از طرف {sender_name} دریافت کردید."
            )  # "You received X points from SenderName."
        except Exception:
            pass  # Ignore errors if the recipient cannot be notified
    else:
        # User cancelled via the inline "لغو" (Cancel) button
        await query.edit_message_text("انتقال لغو شد.")  # "Transfer cancelled."
    return ConversationHandler.END  # End the conversation in either case

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Allows the user to cancel the conversation with /cancel command."""
    await update.message.reply_text("انتقال لغو شد.")  # "Transfer cancelled."
    return ConversationHandler.END

# Define the ConversationHandler with the states and fallbacks
transfer_points_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_TRANSFER}$"), start_transfer)],
    states={
        SELECT_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_recipient)],
        SELECT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_amount)],
        CONFIRM_TRANSFER: [CallbackQueryHandler(confirm_transfer, pattern="^transfer_confirm$|^transfer_cancel$")],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        MessageHandler(filters.Regex("(?i)^cancel$"), cancel)
    ],
)
