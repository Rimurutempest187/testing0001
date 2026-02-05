# handlers/summon.py
from telegram import Update
from telegram.ext import ContextTypes
from db import db
from utils import init_user, choose_chars, summon_animation, add_inventory, add_exp, format_char
from utils import RARITY_RATE
import asyncio

SUMMON_COST = 50
TEN_SUMMON_COST = 500

async def summon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    r = await db.fetchone("SELECT coins FROM users WHERE id=?", (uid,))
    coins = r[0] if r else 0
    if coins < SUMMON_COST:
        await update.message.reply_text("❌ Coins မလုံလောက်ပါ")
        return
    await db.execute("UPDATE users SET coins=coins-? WHERE id=?", (SUMMON_COST, uid), commit=True)
    msg = await update.message.reply_text("🎰 Summon Initializing...")
    await summon_animation(msg)
    chars = await choose_chars(1)
    if not chars:
        await msg.edit_text("⚠ No Character Found")
        return
    ch = chars[0]
    await add_inventory(uid, ch[0])
    leveled, new_lvl = await add_exp(uid, 10)
    caption = "🌟 SUMMON RESULT 🌟\n\n" + await format_char(ch)
    try:
        if ch[6]:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=ch[6], caption=caption)
            try:
                await msg.delete()
            except Exception:
                pass
            if leveled:
                await update.message.reply_text(f"🎉 Level up! အဆင့် {new_lvl} ဖြစ်လာပါသည်")
            return
    except Exception:
        pass
    try:
        await msg.edit_text(caption)
    except Exception:
        await update.message.reply_text(caption)
    if leveled:
        await update.message.reply_text(f"🎉 Level up! အဆင့် {new_lvl} ဖြစ်လာပါသည်")

async def summon10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    r = await db.fetchone("SELECT coins FROM users WHERE id=?", (uid,))
    coins = r[0] if r else 0
    if coins < TEN_SUMMON_COST:
        await update.message.reply_text("❌ Coins မလုံလောက်ပါ")
        return
    await db.execute("UPDATE users SET coins=coins-? WHERE id=?", (TEN_SUMMON_COST, uid), commit=True)
    msg = await update.message.reply_text("🎰 10x Summon Initializing...")
    await summon_animation(msg)
    res = await choose_chars(10)
    text = "🌟 10x SUMMON RESULT 🌟\n\n"
    count = {}
    leveled_any = False
    for ch in res:
        await add_inventory(uid, ch[0])
        leveled, new_lvl = await add_exp(uid, 10)
        if leveled:
            leveled_any = True
        key = f"{ch[1]} ({ch[2]})"
        count[key] = count.get(key, 0) + 1
    for k, v in count.items():
        text += f"{k} x{v}\n"
    try:
        await msg.edit_text(text)
    except Exception:
        await update.message.reply_text(text)
    if leveled_any:
        row = await db.fetchone("SELECT level FROM users WHERE id=?", (uid,))
        if row:
            await update.message.reply_text(f"🎉 Level up! အဆင့် {row[0]} ဖြစ်လာပါသည်")
