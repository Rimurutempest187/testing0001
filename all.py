db.py
import aiosqlite
import os
import time
import shutil
from typing import List, Tuple, Any, Optional

DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "bot.db")
BACKUP_DIR = "backups"

class DB:
    def __init__(self, path: str = DB_FILE):
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None

    async def init(self):
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA synchronous=NORMAL;")
        await self._migrate()

    async def _migrate(self):
        """Create tables if not exist (idempotent)."""
        script = """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            coins INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            last_daily INTEGER DEFAULT 0,
            last_battle INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS characters(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            rarity TEXT,
            faction TEXT,
            power INTEGER,
            price INTEGER,
            file_id TEXT
        );
        CREATE TABLE IF NOT EXISTS inventory(
            user_id INTEGER,
            char_id INTEGER,
            count INTEGER,
            PRIMARY KEY(user_id,char_id)
        );
        CREATE TABLE IF NOT EXISTS admins(
            user_id INTEGER PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS quests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            reward_coins INTEGER DEFAULT 0,
            reward_exp INTEGER DEFAULT 0,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS user_quests(
            user_id INTEGER,
            quest_id INTEGER,
            done INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, quest_id)
        );
        """
        await self.conn.executescript(script)
        await self.conn.commit()

    async def fetchone(self, query: str, params: Tuple = ()):
        cur = await self.conn.execute(query, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def fetchall(self, query: str, params: Tuple = ()):
        cur = await self.conn.execute(query, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows

    async def execute(self, query: str, params: Tuple = (), commit: bool = False):
        cur = await self.conn.execute(query, params)
        if commit:
            await self.conn.commit()
        return cur

    async def backup(self) -> Optional[str]:
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(BACKUP_DIR, f"bot_{timestamp}.db")
            # Make sure writes are flushed
            await self.conn.commit()
            self.conn.close()
            shutil.copy(self.path, backup_file)
            # reopen
            self.conn = await aiosqlite.connect(self.path)
            await self.conn.execute("PRAGMA journal_mode=WAL;")
            await self.conn.execute("PRAGMA synchronous=NORMAL;")
            return backup_file
        except Exception:
            return None

    async def list_backups(self) -> List[str]:
        files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("bot_") and f.endswith(".db")])
        return files

    async def restore_last_backup(self) -> bool:
        files = await self.list_backups()
        if not files:
            return False
        last = os.path.join(BACKUP_DIR, files[-1])
        try:
            self.conn.close()
        except Exception:
            pass
        shutil.copy(last, self.path)
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA synchronous=NORMAL;")
        return True

# single global db instance (import and await db.init() at startup)
db = DB()
```

---

**File: utils.py**

```python
# utils.py
import random
import asyncio
from typing import Tuple, Any, List
from telegram import Message
from telegram.ext import ContextTypes
from db import db

RARITY_RATE = {
    "Common": 50,
    "Rare": 25,
    "Epic": 15,
    "Legendary": 8,
    "Mythic": 2
}
ALLOWED_RARITY = list(RARITY_RATE.keys())

async def is_admin(user_id: int) -> bool:
    if user_id is None:
        return False
    row = await db.fetchone("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    return bool(row)

async def is_owner(user_id: int, owner_id: int) -> bool:
    return user_id == owner_id

async def init_user(user_id: int, start_coins:int = 200):
    await db.execute("INSERT OR IGNORE INTO users(id, coins, level, exp, last_daily, last_battle) VALUES(?,?,?,?,?,?)",
                     (user_id, start_coins, 1, 0, 0, 0), commit=True)

def roll_rarity() -> str:
    r = random.randint(1, 100)
    total = 0
    for k, v in RARITY_RATE.items():
        total += v
        if r <= total:
            return k
    return "Common"

async def add_inventory(user_id: int, char_id: int, amt: int = 1):
    row = await db.fetchone("SELECT count FROM inventory WHERE user_id=? AND char_id=?", (user_id, char_id))
    if row:
        await db.execute("UPDATE inventory SET count = count + ? WHERE user_id=? AND char_id=?", (amt, user_id, char_id), commit=True)
    else:
        await db.execute("INSERT INTO inventory(user_id, char_id, count) VALUES(?,?,?)", (user_id, char_id, amt), commit=True)

async def add_exp(user_id: int, amt: int = 0):
    row = await db.fetchone("SELECT level,exp FROM users WHERE id=?", (user_id,))
    if not row:
        return False, None
    lvl, exp = row
    exp += amt
    leveled = False
    while exp >= lvl * 100:
        exp -= lvl * 100
        lvl += 1
        leveled = True
    await db.execute("UPDATE users SET level=?, exp=? WHERE id=?", (lvl, exp, user_id), commit=True)
    return leveled, lvl

async def format_char(row: Tuple[Any, ...]) -> str:
    # row: (id, name, rarity, faction, power, price, file_id)
    return (
        f"🆔 ID: {row[0]}\n"
        f"✨ Name: {row[1]}\n"
        f"⭐ Rarity: {row[2]}\n"
        f"🏹 Faction: {row[3]}\n"
        f"💪 Power: {row[4]}\n"
        f"💰 Price: {row[5]}"
    )

async def get_total_power(user_id: int) -> int:
    row = await db.fetchone(
        "SELECT SUM(characters.power * inventory.count) FROM inventory JOIN characters ON inventory.char_id = characters.id WHERE inventory.user_id=?",
        (user_id,)
    )
    return int(row[0] or 0)

async def safe_edit_message(msg: Message, text: str):
    try:
        if getattr(msg, "photo", None):
            try:
                await msg.edit_caption(text)
                return
            except Exception:
                pass
        await msg.edit_text(text)
    except Exception:
        try:
            await msg.reply_text(text)
        except Exception:
            pass

async def get_user_name(bot, user_id: int) -> str:
    try:
        user = await bot.get_chat(user_id)
        if getattr(user, "username", None):
            return "@" + user.username
        if getattr(user, "first_name", None):
            return user.first_name
        return str(user_id)
    except Exception:
        return str(user_id)

async def summon_animation(msg: Message):
    frames = [
        "🎰 Summoning...",
        "✨ Charging Mana...",
        "🌌 Opening Portal...",
        "⚡ Power Rising...",
        "💥 Breaking Seal...",
        "🌟 Revealing..."
    ]
    for f in frames:
        try:
            await msg.edit_text(f)
        except Exception:
            pass
        await asyncio.sleep(0.9)

async def battle_animation(msg: Message, me: str, enemy: str):
    frames = [
        f"⚔ {me}  VS  {enemy}\n\n🔥 Preparing...",
        f"⚔ {me}  VS  {enemy}\n\n3️⃣ Ready...",
        f"⚔ {me}  VS  {enemy}\n\n2️⃣ Ready...",
        f"⚔ {me}  VS  {enemy}\n\n1️⃣ Ready...",
        f"💥 BATTLE START 💥\n\n{me} ➡ ⚔ ➡ {enemy}",
        f"💢 {enemy} Counter Attack!",
        f"🔥 Massive Damage!",
        f"⚡ Final Hit..."
    ]
    for f in frames:
        try:
            await msg.edit_text(f)
        except Exception:
            pass
        await asyncio.sleep(1.0)

async def choose_chars(n: int) -> List[Tuple]:
    rows = await db.fetchall("SELECT * FROM characters") or []
    if not rows:
        return []
    res = []
    for _ in range(n):
        r = roll_rarity()
        pool = [x for x in rows if x[2] == r] or rows
        res.append(random.choice(pool))
    return res
```

---

**Folder: handlers/**

**File: handlers/basic.py**

```python
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
    "/inventory - ကုန်အိတ်\n"
    "/daily - နေ့စဉ်ဆုပေး\n"
    "/balance - ချွေတာ\n"
    "/tops - အဆင့်စား\n"
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
```

---

**File: handlers/summon.py**

```python
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
