
```

---


```

---

**Folder: handlers/**

```

---

```

---

**File: handlers/store.py**

```python
# handlers/store.py
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
```

---

**File: handlers/inventory.py**

```python
# handlers/inventory.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import db
from utils import init_user

INV_PAGE = 8

async def build_inventory_pages(uid: int):
    rows = await db.fetchall(
        "SELECT characters.id, characters.name, characters.rarity, inventory.count FROM inventory JOIN characters ON inventory.char_id=characters.id WHERE inventory.user_id=? ORDER BY characters.id",
        (uid,)
    ) or []
    pages = [rows[i:i+INV_PAGE] for i in range(0, len(rows), INV_PAGE)]
    return pages

async def send_inventory_page(chat_id: int, context: ContextTypes.DEFAULT_TYPE, pages, idx: int):
    page = pages[idx]
    text = f"📦 Inventory Page {idx+1}/{len(pages)}\n\n"
    for i, row in enumerate(page, 1):
        cid, name, rarity, count = row
        text += f"{i}. {name} ({rarity}) x{count} — ID:{cid}\n"
    buttons = []
    nav_buttons = []
    if idx > 0:
        nav_buttons.append(InlineKeyboardButton("⬅ Prev", callback_data=f"inv_{idx-1}"))
    if idx < len(pages)-1:
        nav_buttons.append(InlineKeyboardButton("Next ➡", callback_data=f"inv_{idx+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    await context.bot.send_message(chat_id, text, reply_markup=reply_markup)

async def inventory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await init_user(uid)
    pages = await build_inventory_pages(uid)
    if not pages:
        await update.message.reply_text("📦 Inventory သာမန်အားဖြင့် ဗလာပါ")
        return
    await send_inventory_page(update.effective_chat.id, context, pages, 0)

async def inv_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pages = await build_inventory_pages(uid)
    if not pages:
        await q.message.reply_text("📦 Inventory ဗလာပါ")
        return
    try:
        idx = int(q.data.split("_")[1])
    except Exception:
        idx = 0
    try:
        await q.message.delete()
    except Exception:
        pass
    await send_inventory_page(q.message.chat.id, context, pages, idx)
```

---

**File: handlers/battle.py**

```python
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
```

---

**File: handlers/admin.py**

```python
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
```

---

**File: handlers/quest.py**

```python
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
```

---

**File: main.py (skeleton)**

```python
# main.py (skeleton) — minimal startup that wires handlers
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from db import db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

async def main():
    await db.init()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # import handlers
    from handlers.basic import start, balance, profile, tops_cmd
    from handlers.summon import summon, summon10
    from handlers.store import store_cmd, store_btn
    from handlers.inventory import inventory_cmd, inv_btn
    from handlers.admin import addadmin_cmd, removeadmin_cmd, admins_cmd, addcoins_cmd, upload_cmd
    from handlers.battle import battle_cmd
    from handlers.quest import createquest_cmd, delquest_cmd, quest_cmd, claim_cmd

    # register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("tops", tops_cmd))

    app.add_handler(CommandHandler("summon", summon))
    app.add_handler(CommandHandler("summon10", summon10))

    app.add_handler(CommandHandler("store", store_cmd))
    app.add_handler(CallbackQueryHandler(store_btn, pattern=r'^(buy_\d+|next_store)$'))

    app.add_handler(CommandHandler("inventory", inventory_cmd))
    app.add_handler(CallbackQueryHandler(inv_btn, pattern=r'^inv_\d+$'))

    app.add_handler(CommandHandler("upload", upload_cmd))
    app.add_handler(CommandHandler("addadmin", addadmin_cmd))
    app.add_handler(CommandHandler("removeadmin", removeadmin_cmd))
    app.add_handler(CommandHandler("admins", admins_cmd))
    app.add_handler(CommandHandler("addcoins", addcoins_cmd))

    app.add_handler(CommandHandler("battle", battle_cmd))

    app.add_handler(CommandHandler("createquest", createquest_cmd))
    app.add_handler(CommandHandler("delquest", delquest_cmd))
    app.add_handler(CommandHandler("quest", quest_cmd))
    app.add_handler(CommandHandler("claim", claim_cmd))

    print("Bot started")
    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
