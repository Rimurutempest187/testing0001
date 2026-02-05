# handlers/quest.py
from telegram import Update
from telegram.ext import ContextTypes
from db import db
from utils import init_user, add_exp

async def createquest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # owner check left to caller
    text_args = " ".join(context.args).strip()
    if not text_args:
        await update.message.reply_text("Usage: /createquest Name|Coins|Exp|Description")
        return
    parts = [p.strip() for p in text_args.split("|")]
    if len(parts) < 4:
        await update.message.reply_text("Usage: /createquest Name|Coins|Exp|Description")
        return
    name, coins_s, exp_s, desc = parts[0], parts[1], parts[2], parts[3]
    try:
        coins = int(coins_s); expv = int(exp_s)
    except Exception:
        await update.message.reply_text("Coins နှင့် Exp သည် ဂဏန်းဖြစ်ရပါမယ်")
        return
    await db.execute("INSERT INTO quests(name, reward_coins, reward_exp, description) VALUES(?,?,?,?)", (name, coins, expv, desc), commit=True)
    await update.message.reply_text("✅ Quest created")

async def delquest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_args = context.args
    if len(text_args) != 1:
        await update.message.reply_text("Usage: /delquest <quest_id>")
        return
    try:
        qid = int(text_args[0])
    except Exception:
        await update.message.reply_text("Invalid quest_id")
        return
    await db.execute("DELETE FROM quests WHERE id=?", (qid,), commit=True)
    await db.execute("DELETE FROM user_quests WHERE quest_id=?", (qid,), commit=True)
    await update.message.reply_text("✅ Quest deleted (if existed)")

async def quest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    rows = await db.fetchall("SELECT id, name, reward_coins, reward_exp, description FROM quests") or []
    if not rows:
        await update.message.reply_text("📜 Quest မရှိသေးပါ")
        return
    claimed = await db.fetchall("SELECT quest_id FROM user_quests WHERE user_id=? AND done=1", (uid,)) or []
    claimed_set = {r[0] for r in claimed}
    text = "📜 Quest List:\n\n"
    for r in rows:
        qid, name, coins, expv, desc = r
        status = "✅ Claimed" if qid in claimed_set else "🔹 Available"
        text += f"ID:{qid} {status}\n{name}\n{desc}\nReward: {coins} coins, {expv} EXP\n\n"
    text += "Claim အတွက်: /claim <quest_id>"
    await update.message.reply_text(text)

async def claim_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /claim <quest_id>")
        return
    try:
        qid = int(context.args[0])
    except Exception:
        await update.message.reply_text("Invalid quest_id")
        return
    q = await db.fetchone("SELECT reward_coins, reward_exp FROM quests WHERE id=?", (qid,))
    if not q:
        await update.message.reply_text("Quest မတွေ့ပါ")
        return
    row = await db.fetchone("SELECT done FROM user_quests WHERE user_id=? AND quest_id=?", (uid, qid))
    if row and row[0] == 1:
        await update.message.reply_text("❌ သင်သည် ဒီ Quest ကို ရယူပြီးသားဖြစ်သည်")
        return
    await db.execute("INSERT OR REPLACE INTO user_quests(user_id, quest_id, done) VALUES(?,?,1)", (uid, qid, 1), commit=True)
    coins, expv = q
    await db.execute("UPDATE users SET coins = coins + ? WHERE id=?", (coins, uid), commit=True)
    leveled, new_lvl = await add_exp(uid, expv)
    msg = f"🎉 Quest claimed! +{coins} coins, +{expv} EXP"
    if leveled:
        msg += f"\n🎊 Level up! အဆင့် {new_lvl}"
    await update.message.reply_text(msg)
