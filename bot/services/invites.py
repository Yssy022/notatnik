from db.crud import create_invite_code, list_invite_codes, get_invite_code
from db.database import AsyncSessionLocal


async def generate_invite(admin_id: int, max_uses: int = 1) -> str:
    async with AsyncSessionLocal() as db:
        invite = await create_invite_code(db, admin_id, max_uses)
        return invite.code


async def get_invites_list() -> list:
    async with AsyncSessionLocal() as db:
        return await list_invite_codes(db)
