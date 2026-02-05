from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from db import db
from utils import format_char, add_inventory
import random

async def send_store(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    chars = await db.fetchall("SELECT * FROM characters")
    if not chars:
        await context.bot.send_message(chat_id, "⚠ Store ထဲမှာ Character မရှိသေးပါ")
        return
    char = random.choice(chars)
    keyboard = [[
        InlineKeyboardButton("🛒 Buy", callback_data=f"buy_{char[0]}"),
        InlineKeyboardButton("➡ Next", callback_data="next_store")
    ]]
    markup = InlineKeyboardMarkup(keyboard)
    caption = await format_char(char)
    if char[6]:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=char[6], caption=caption, reply_markup=markup)
            return
        except Exception:
            pass
    await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=markup)

async def store_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_store(update.effective_chat.id, context)

async def store_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data
    msg = q.message
    if data == "next_store":
        try:
            await msg.delete()
        except Exception:
            pass
        await send_store(msg.chat.id, context)
        return
    if data.startswith("buy_"):
        try:
            cid = int(data.split("_")[1])
        except Exception:
            await q.answer("Invalid ID", show_alert=True)
            return
        char = await db.fetchone("SELECT * FROM characters WHERE id=?", (cid,))
        if not char:
            await q.edit_message_text("❌ Character မတွေ့ပါ")
            return
        row = await db.fetchone("SELECT coins FROM users WHERE id=?", (uid,))
        coins = row[0] if row else 0
        if coins < char[5]:
            await q.edit_message_text("❌ Coins မလုံလောက်ပါ")
            return
        await db.execute("UPDATE users SET coins=coins-? WHERE id=?", (char[5], uid), commit=True)
        await add_inventory(uid, cid)
        await q.edit_message_text(f"✅ Successfully Bought!\n\n📦 {char[1]} ({char[2]})")
