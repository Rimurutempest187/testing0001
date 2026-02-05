
```

---


```

---

**Folder: handlers/**

```

---

```

---


```

---

```

---

*
```

---

```

```python
---


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
