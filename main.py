import os
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# Common
from .handlers.common import start, check_status

# Admin commands
from .handlers.admin import (
    unlimit_today, notify_all, give_yellow,
    assign_task, list_users, remove_yellow, set_name,
    activate_user, deactivate_user, list_inactive

)

# Attendance
from .handlers.attendance import (
    handle_checkin, handle_checkout,
    my_checkins, my_checkouts, my_yellow_cards
)

# Leaderboard
from .handlers.leaderboard import my_scores

# Tasks
from .handlers.tasks import show_tasks, task_done

# Credits
from .handlers.credits import (
    my_balance, withdraw, my_balance_button,
    withdraw_button, handle_withdraw_amount,
    list_withdraws, reject_withdraw,
    approve_withdraw, pending_withdraws,handle_withdraw_action
)
from .config import (
    BTN_CHECKIN, BTN_CHECKOUT,
    BTN_MY_INS, BTN_MY_OUTS,
    BTN_YELLOWS, BTN_MY_TASKS,
    BTN_SCORES, BTN_BALANCE, BTN_WITHDRAW
)
def build_app(token: str):
    app = ApplicationBuilder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("unlimit", unlimit_today))

    # Keyboard text handlers
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_CHECKIN}$"), handle_checkin))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_CHECKOUT}$"), handle_checkout))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_MY_INS}$"), my_checkins))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_MY_OUTS}$"), my_checkouts))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_YELLOWS}$"), my_yellow_cards))
    app.add_handler(CommandHandler("notify", notify_all))
    app.add_handler(CommandHandler("yellow", give_yellow))
    app.add_handler(CommandHandler("task", assign_task))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_MY_TASKS}$"), show_tasks))
    app.add_handler(CallbackQueryHandler(task_done, pattern=r"^done:"))
    app.add_handler(CommandHandler("list_users", list_users))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_SCORES}$"), my_scores))
    app.add_handler(CommandHandler("remove_yellow", remove_yellow))
    app.add_handler(CommandHandler("setname", set_name))
    app.add_handler(CommandHandler("my_balance", my_balance))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("list_withdraws", list_withdraws))
    app.add_handler(CommandHandler("reject_withdraw", reject_withdraw))
    app.add_handler(CommandHandler("approve_withdraw", approve_withdraw))
    app.add_handler(CommandHandler("pending_withdraws", pending_withdraws))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_BALANCE}$"), my_balance_button))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(f"^{BTN_WITHDRAW}$"), withdraw_button))
# catch numbers typed after withdraw button
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^\d+$"), handle_withdraw_amount))
    app.add_handler(CallbackQueryHandler(handle_withdraw_action, pattern=r"^withdraw_action:"))
    app.add_handler(CommandHandler("activate", activate_user))
    app.add_handler(CommandHandler("deactivate", deactivate_user))
    app.add_handler(CommandHandler("list_inactive", list_inactive))
    app.add_handler(CallbackQueryHandler(check_status, pattern=r"^check_status:"))

    return app


def main():
    token = "7751184895:AAEWHV3N3q1mjsN2d1LOMzvCbsgJtTPrJu0"
    app = build_app(token)
    app.run_polling()

if __name__ == "__main__":
    main()
