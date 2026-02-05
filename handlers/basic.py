# handlers/basic.py
from telegram import Update
from telegram.ext import ContextTypes
from db import db
from utils import init_user, format_char, get_user_name

START_TEXT = (
    "🎮 Tensura World Gacha\n\n"
    "📌 Commands (မြန်မာ)\n\n"
    "/profile - မိမိအချက်အလက်\n"
    "/summon - Summon x1\n"
    "/summon10 - Summon x10\n"
    "/store - ဆိုင်\n"
    "/inventory - အိတ်\n"
    "/daily - နေ့စဉ်ဆု\n"
    "/balance - ငွေစစ်ရန်\n"
    "/tops - အဆင့်\n"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    await update.message.reply_text(START_TEXT)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    r = await db.fetchone("SELECT coins FROM users WHERE id=?", (uid,))
    coins = r[0] if r else 0
    await update.message.reply_text(f"💰 Coins: {coins}")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    r = await db.fetchone("SELECT level, exp, coins FROM users WHERE id=?", (uid,))
    if not r:
        await update.message.reply_text("Profile မရပါ")
        return
    lvl, exp, coins = r
    total_power_row = await db.fetchone("SELECT SUM(characters.power * inventory.count) FROM inventory JOIN characters ON inventory.char_id = characters.id WHERE inventory.user_id=?", (uid,))
    total_power = int(total_power_row[0] or 0)
    text = (
        f"👤 Profile\n\n"
        f"🆔 ID: {uid}\n"
        f"🎚 Level: {lvl}\n"
        f"📊 EXP: {exp}/{lvl*100}\n"
        f"💰 Coins: {coins}\n"
        f"🏋️ Total Power: {total_power}"
    )
    await update.message.reply_text(text)

async def tops_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db.fetchall("SELECT id, level, exp, coins FROM users ORDER BY level DESC, exp DESC, coins DESC LIMIT 10") or []
    if not rows:
        await update.message.reply_text("⚠ User မရှိသေးပါ")
        return
    text = "🏆 <b>Top Players Ranking</b>\n\n"
    for idx, row in enumerate(rows, 1):
        uid, lvl, exp, coins = row
        name = await get_user_name(context.bot, uid)
        text += (
            f"#{idx} {name}\n"
            f"   🎚 Level: {lvl}\n"
            f"   💰 Coins: {coins}\n"
            f"   📊 EXP: {exp}\n\n"
        )
    await update.message.reply_text(text, parse_mode="HTML")
