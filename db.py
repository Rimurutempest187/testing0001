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
