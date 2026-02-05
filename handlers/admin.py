# handlers/admin.py
from telegram import Update
from telegram.ext import ContextTypes
from db import db
from utils import is_admin, is_owner, init_user

async def addadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_owner(uid, int(context.bot.owner_id)):
        await update.message.reply_text("⚠ Owner only command")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        target = int(context.args[0])
    except Exception:
        await update.message.reply_text("Invalid user_id")
        return
    await db.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (target,), commit=True)
    await update.message.reply_text(f"✅ {target} ကို admin ပေးပြီးပါပြီ")

async def removeadmin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_owner(uid, int(context.bot.owner_id)):
        await update.message.reply_text("⚠ Owner only command")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        target = int(context.args[0])
    except Exception:
        await update.message.reply_text("Invalid user_id")
        return
    await db.execute("DELETE FROM admins WHERE user_id=?", (target,), commit=True)
    await update.message.reply_text(f"✅ {target} ကို admin အဖြစ် ဖယ်ရှားပြီးပါပြီ")

async def admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.fetchall("SELECT user_id FROM admins") or []
    if not rows:
        await update.message.reply_text("Admin မရှိသေးပါ")
        return
    text = "🛡 Admin List:\n\n"
    for r in rows:
        text += f"- {r[0]}\n"
    await update.message.reply_text(text)

async def addcoins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user.id
    if not await is_admin(admin):
        await update.message.reply_text("⚠ Admin only")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠ User ကို reply လုပ်ပြီး /addcoins <amount>")
        return
    target = update.message.reply_to_message.from_user.id
    await init_user(target)
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /addcoins <amount>")
        return
    try:
        amount = int(context.args[0])
    except Exception:
        await update.message.reply_text("❌ Amount မမှန်ပါ")
        return
    if amount <= 0:
        await update.message.reply_text("❌ Amount must be > 0")
        return
    await db.execute("UPDATE users SET coins = coins + ? WHERE id=?", (amount, target), commit=True)
    await update.message.reply_text(f"✅ Added {amount} coins to {update.message.reply_to_message.from_user.first_name}")

async def upload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user.id
    if not await is_admin(admin):
        await update.message.reply_text("⚠ Admin မဟုတ်ပါ")
        return
    photo_msg = None
    if update.message.photo:
        photo_msg = update.message
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo_msg = update.message.reply_to_message
    if not photo_msg:
        await update.message.reply_text("📷 /upload လုပ်ချင်ရင် photo တစ်ပုံပို့ပါ သို့မဟုတ် photo ကို reply လုပ်ပြီး /upload")
        return
    args_text = " ".join(context.args).strip()
    if not args_text:
        caption = update.message.caption or (update.message.reply_to_message.caption if update.message.reply_to_message else "")
        if not caption:
            await update.message.reply_text("Usage: /upload Name|Rarity|Faction|Power|Price  OR attach caption lines (Name: X)")
            return
        data = {}
        for line in caption.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            data[k.strip().lower()] = v.strip()
        required = ["name", "rarity", "faction", "power", "price"]
        if not all(k in data for k in required):
            await update.message.reply_text("Caption မှာ name, rarity, faction, power, price သေချာရေးပါ")
            return
        try:
            power = int(data["power"])
            price = int(data["price"])
        except Exception:
            await update.message.reply_text("Power နှင့် Price က ဂဏန်းဖြစ်ရပါမယ်")
            return
        name = data["name"]
        rarity = data["rarity"]
        faction = data["faction"]
    else:
        parts = [p.strip() for p in args_text.split("|")]
        if len(parts) != 5:
            await update.message.reply_text("Usage: /upload Name|Rarity|Faction|Power|Price")
            return
        try:
            name, rarity, faction, power_s, price_s = parts
            power = int(power_s)
            price = int(price_s)
        except Exception:
            await update.message.reply_text("Power နှင့် Price က ဂဏန်းဖြစ်ရပါမယ်")
            return
    if rarity not in [r for r in ['Common','Rare','Epic','Legendary','Mythic']]:
        await update.message.reply_text(f"Rarity က Common, Rare, Epic, Legendary, Mythic အထဲမှတစ်ခုဖြစ်ရမယ်")
        return
    file_id = photo_msg.photo[-1].file_id
    cur = await db.execute("INSERT INTO characters (name, rarity, faction, power, price, file_id) VALUES (?,?,?,?,?,?)", (name, rarity, faction, power, price, file_id), commit=True)
    # try to fetch last id
    row = await db.fetchone("SELECT id FROM characters WHERE name=? ORDER BY id DESC LIMIT 1", (name,))
    new_id = row[0] if row else None
    await update.message.reply_text(f"✅ Uploaded! ID: {new_id} | Name: {name}")
