from pytz import timezone

# Core settings
LOCAL_TZ = timezone("Asia/Tehran")   # operational TZ
DATA_FILE = "worker_days_off.json"   # existing JSON store

# Defaults / business rules
DEFAULT_CHECKIN_LIMIT = "08:31"       # HH:MM (24h)
EARLY_BIRD_WINDOW_MIN = 120           # minutes window for early ladder

# Admins (ADD YOUR ADMIN IDS)
ADMIN_IDS = {5963270398}  # example: General | Aref 🏅

# UI labels (Persian)
BTN_SCORES = "⭐️ امتیازات"
BTN_CHECKIN = "✅ من رسیدم"
BTN_CHECKOUT = "🏁 من رفتم"
BTN_MY_INS = "📋 ورود های من"
BTN_MY_OUTS = "🏁 خروج های من"
BTN_MY_LEAVES = "📅 مرخصی هام"
BTN_REQUEST_LEAVE = "📘 دریافت مرخصی"
BTN_MY_TASKS = "📝 MY TASKS"
BTN_YELLOWS = "📒 کارت های زرد من"
BTN_BALANCE = "💰 بانک من"
BTN_WITHDRAW = "📤 درخواست برداشت"
BTN_TRANSFER = "🔄 انتقال امتیاز"

MAIN_MENU = [
    [BTN_CHECKIN, BTN_CHECKOUT],
    [BTN_MY_INS, BTN_MY_OUTS],
    [BTN_MY_LEAVES, BTN_REQUEST_LEAVE],
    [BTN_MY_TASKS, BTN_YELLOWS],
    [BTN_SCORES, BTN_BALANCE, BTN_WITHDRAW, BTN_TRANSFER]
]

ADMIN_COMMAND_BUTTONS = [
    ["/unlimit", "/notify", "/yellow"],
    ["/remove_yellow", "/setname", "/task"],
    ["/list_users", "/list_inactive"],
    ["/activate", "/deactivate", "/remove_user"],
    ["/list_withdraws", "/pending_withdraws"],
    ["/approve_withdraw", "/reject_withdraw"],
]

ADMIN_MENU = [row[:] for row in MAIN_MENU] + ADMIN_COMMAND_BUTTONS
