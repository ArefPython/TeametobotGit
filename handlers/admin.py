from datetime import date
from telegram import Update
from telegram.ext import ContextTypes
from ..config import ADMIN_IDS
from ..storage import read_all, write_all, ensure_config, get_user
from uuid import uuid4
from datetime import datetime



def _msg(update: Update):
    return update.effective_message


async def unlimit_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")
    db = await read_all()
    cfg = await ensure_config(db)
    today = date.today().isoformat()
    if today not in cfg["unlimited_dates"]:
        cfg["unlimited_dates"].append(today)
        await write_all(db)
    await msg.reply_text("امروز محدودیت ورود برداشته شد ✅")

async def notify_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: broadcast a message to all users."""
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if not args:
        return await msg.reply_text("❗️ لطفا متن پیام را بعد از /notify وارد کنید.")

    message = " ".join(args)
    db = await read_all()
    count = 0

    for uid in db:
        if uid == "_config":
            continue
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"📢 {message}")
            count += 1
        except Exception:
            pass

    await msg.reply_text(f"پیام برای {count} نفر ارسال شد ✅")
async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: set or update a user's display name."""
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if len(args) < 2:
        return await msg.reply_text("❗️ استفاده: /setname <user_id> <display name>")

    target_id = args[0]
    new_name = " ".join(args[1:])

    db = await read_all()
    user = await get_user(db, target_id)

    old_name = user.get("display_name") or user.get("username") or target_id
    user["display_name"] = new_name
    await write_all(db)

    await msg.reply_text(f"نام کاربر تغییر یافت:\n{old_name} → {new_name}")

    # notify user
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"👤 نام شما توسط مدیریت تغییر یافت:\n{new_name}"
        )
    except Exception:
        pass

async def remove_yellow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: remove a yellow card from a user by index."""
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if len(args) < 2:
        return await msg.reply_text("❗️ استفاده: /remove_yellow <user_id> <index>")

    target_id = args[0]
    try:
        index = int(args[1]) - 1
    except ValueError:
        return await msg.reply_text("❗️ شماره کارت زرد باید عدد باشد.")

    db = await read_all()
    user = await get_user(db, target_id)

    cards = user.get("yellow_cards", [])
    if not cards:
        return await msg.reply_text("❗️ این کاربر هیچ کارت زردی ندارد.")
    if index < 0 or index >= len(cards):
        return await msg.reply_text("❗️ شماره کارت زرد نامعتبر است.")

    removed = cards.pop(index)
    await write_all(db)

    display = user.get("display_name") or user.get("username") or target_id

    # notify user
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"⚠️ یک کارت زرد شما توسط مدیریت حذف شد.\n❌ {removed}"
        )
    except Exception:
        pass

    await msg.reply_text(f"کارت زرد شماره {index+1} برای {display} حذف شد ✅")



async def give_yellow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: manually assign a yellow card with a reason."""
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if len(args) < 2:
        return await msg.reply_text("❗️ استفاده: /yellow <user_id> <reason>")

    target_id = args[0]
    reason = " ".join(args[1:])

    db = await read_all()
    user = await get_user(db, target_id)

    # record yellow card
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"کارت زرد (اداری) در {now}: {reason}"
    user.setdefault("yellow_cards", []).append(entry)

    await write_all(db)

    display = user.get("display_name") or user.get("username") or target_id

    # notify target user
    try:
        await context.bot.send_message(chat_id=int(target_id), text=f"⚠️ شما یک کارت زرد گرفتید: {reason}")
    except Exception:
        pass

    # broadcast to everyone
    text = f"📢 {display} یک کارت زرد گرفت ({reason})"
    for uid in db:
        if uid == "_config":
            continue
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
        except Exception:
            pass

    await msg.reply_text(f"کارت زرد برای {display} ثبت شد ✅")

async def assign_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: assign a task to a specific user."""
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if len(args) < 2:
        return await msg.reply_text("❗️ استفاده: /task <user_id> <task text>")

    target_id = args[0]
    task_text = " ".join(args[1:])
    task_id = str(uuid4())[:8]

    db = await read_all()
    user = await get_user(db, target_id)

    task_entry = {"id": task_id, "text": task_text}
    user.setdefault("tasks", []).append(task_entry)
    await write_all(db)

    display = user.get("display_name") or user.get("username") or target_id

    # notify target user
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"📌 شما یک مأموریت جدید دارید:\n{task_text}\n(برای مشاهده: 📝 MY TASKS)"
        )
    except Exception:
        pass

    await msg.reply_text(f"ماموریت برای {display} ثبت شد ✅")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    db = await read_all()
    lines = ["👥 لیست کاربران:"]
    for uid, user in db.items():
        if uid == "_config":
            continue
        uname = user.get("username") or "—"
        dname = user.get("display_name") or "—"
        status = "✅ فعال" if user.get("active", False) else "❌ غیرفعال"
        lines.append(f"{uid} → @{uname} / {dname} ({status})")

    if len(lines) == 1:
        return await msg.reply_text("❗️ هیچ کاربری ثبت نشده است.")
    await msg.reply_text("\n".join(lines))


async def activate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")
    args = context.args or []
    if not args:
        return await msg.reply_text("❗️ استفاده: /activate <user_id>")

    target_id = args[0]
    db = await read_all()
    user = db.get(target_id)
    if not user:
        return await msg.reply_text("❗️ کاربر پیدا نشد.")

    user["active"] = True
    await write_all(db)

    await msg.reply_text(f"✅ کاربر {target_id} فعال شد.")
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text="✅ حساب شما توسط مدیریت فعال شد. حالا می‌توانید از امکانات استفاده کنید."
        )
    except Exception:
        pass


async def deactivate_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")
    args = context.args or []
    if not args:
        return await msg.reply_text("❗️ استفاده: /deactivate <user_id>")

    target_id = args[0]
    db = await read_all()
    user = db.get(target_id)
    if not user:
        return await msg.reply_text("❗️ کاربر پیدا نشد.")

    user["active"] = False
    await write_all(db)

    await msg.reply_text(f"❌ کاربر {target_id} غیرفعال شد.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: remove a user from the bot (delete from worker_days_off.json)."""
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    args = context.args or []
    if not args:
        return await msg.reply_text("❗️ استفاده: /remove_user <user_id>")

    target_id = args[0]
    db = await read_all()
    if target_id not in db or target_id == "_config":
        return await msg.reply_text("❗️ کاربر پیدا نشد یا قابل حذف نیست.")

    del db[target_id]
    await write_all(db)

    await msg.reply_text(f"کاربر {target_id} با موفقیت حذف شد ✅")
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text="⛔️ حساب شما توسط مدیریت حذف شد. دیگر نمی‌توانید از امکانات استفاده کنید."
        )
    except Exception:
        pass

async def list_inactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = _msg(update)
    if msg is None:
        return
    tg_user = update.effective_user
    if tg_user is None or tg_user.id not in ADMIN_IDS:
        return await msg.reply_text("⛔️ دسترسی ندارید.")

    db = await read_all()
    lines = ["❌ کاربران غیرفعال:"]
    found = False
    for uid, user in db.items():
        if uid == "_config":
            continue
        if not user.get("active", False):
            found = True
            name = user.get("display_name") or user.get("username") or uid
            lines.append(f"{uid} → {name}")

    if not found:
        return await msg.reply_text("✅ هیچ کاربر غیرفعالی وجود ندارد.")
    await msg.reply_text("\n".join(lines))