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
