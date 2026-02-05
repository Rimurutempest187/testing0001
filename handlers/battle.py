# handlers/battle.py
from telegram import Update
from telegram.ext import ContextTypes
from db import db
from utils import init_user, get_total_power, battle_animation, add_exp, get_user_name
import time
import random

BATTLE_CD = 600

async def battle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    enemy_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        enemy_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            enemy_id = int(context.args[0])
        except Exception:
            enemy_id = None
    if not enemy_id:
        await update.message.reply_text("မှားနေသည် — တိုက်ချင်သူ၏ message ကို reply လုပ်ပြီး `/battle` လို့ပို့ပါ။")
        return
    if enemy_id == uid:
        await update.message.reply_text("ကိုယ့်ကိုယ်ကို မတိုက်နိုင်ပါ")
        return
    await init_user(enemy_id)
    now = int(time.time())
    row = await db.fetchone("SELECT last_battle FROM users WHERE id=?", (uid,))
    last = row[0] if row else 0
    if now - last < BATTLE_CD:
        left = BATTLE_CD - (now-last)
        await update.message.reply_text(f"⏱ {left//60} မိနစ်နောက်မှ ပြန်တိုက်ပါ")
        return
    row2 = await db.fetchone("SELECT last_battle FROM users WHERE id=?", (enemy_id,))
    enemy_last = row2[0] if row2 else 0
    if now - enemy_last < 10:
        await update.message.reply_text("Opponent is busy, try again a bit later.")
        return
    my_power = await get_total_power(uid)
    enemy_power = await get_total_power(enemy_id)
    if my_power == 0 or enemy_power == 0:
        await update.message.reply_text("⚠ တိုက်ရန် characters မရှိသေးပါ")
        return
    me_name = update.effective_user.first_name or str(uid)
    enemy_name = await get_user_name(context.bot, enemy_id)
    try:
        msg = await update.message.reply_text("⚔ Battle Initializing...")
    except Exception:
        msg = None
    if msg:
        await battle_animation(msg, me_name, enemy_name)
    if my_power > enemy_power:
        winner = uid; loser = enemy_id; win_name = me_name
    elif my_power < enemy_power:
        winner = enemy_id; loser = uid; win_name = enemy_name
    else:
        winner = random.choice([uid, enemy_id])
        loser = enemy_id if winner == uid else uid
        win_name = me_name if winner == uid else enemy_name
    reward = random.randint(80, 150)
    await db.execute("UPDATE users SET coins=coins+?, last_battle=? WHERE id=?", (reward, now, winner), commit=True)
    await db.execute("UPDATE users SET last_battle=? WHERE id=?", (now, loser), commit=True)
    await add_exp(winner, 40); await add_exp(loser, 15)
    final_text = (
        f"🏆 BATTLE RESULT 🏆\n\n"
        f"🔥 {me_name}: {my_power}\n"
        f"💀 {enemy_name}: {enemy_power}\n\n"
        f"👑 Winner: {win_name}\n"
        f"💰 +{reward} Coins\n"
        f"⭐ +40 EXP"
    )
    if msg:
        await msg.edit_text(final_text)
    else:
        await update.message.reply_text(final_text)
