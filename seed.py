"""
Seed script — creates the first admin invite code.
Usage: python seed.py
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from db.database import init_db, AsyncSessionLocal
from db.crud import create_invite_code

ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        invite = await create_invite_code(db, ADMIN_ID, max_uses=1)
    bot_name = os.getenv("BOT_USERNAME", "your_bot")
    print(f"\n✅ Seed invite code created!")
    print(f"   Code: {invite.code}")
    print(f"   Link: https://t.me/{bot_name}?start={invite.code}\n")


if __name__ == "__main__":
    asyncio.run(main())
