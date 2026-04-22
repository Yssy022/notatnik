from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from .models import User, InviteCode, Category, Idea, ReminderConfig
from datetime import datetime, timedelta
from typing import Optional
import secrets
import string


# ── USERS ──────────────────────────────────────────────────────────────────────

async def get_user(db: AsyncSession, telegram_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, telegram_id: int, username: Optional[str], invite_code: str) -> User:
    user = User(telegram_id=telegram_id, username=username, invite_code_used=invite_code)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def ban_user(db: AsyncSession, telegram_id: int) -> bool:
    user = await get_user(db, telegram_id)
    if not user:
        return False
    user.is_active = False
    await db.commit()
    return True


async def unban_user(db: AsyncSession, telegram_id: int) -> bool:
    user = await get_user(db, telegram_id)
    if not user:
        return False
    user.is_active = True
    await db.commit()
    return True


async def get_all_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def delete_user_all_data(db: AsyncSession, telegram_id: int) -> bool:
    user = await get_user(db, telegram_id)
    if not user:
        return False
    await db.delete(user)
    await db.commit()
    return True


# ── INVITE CODES ───────────────────────────────────────────────────────────────

async def create_invite_code(db: AsyncSession, admin_id: int, max_uses: int = 1) -> InviteCode:
    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(12))
    invite = InviteCode(code=code, created_by_admin=admin_id, max_uses=max_uses)
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def get_invite_code(db: AsyncSession, code: str) -> Optional[InviteCode]:
    result = await db.execute(select(InviteCode).where(InviteCode.code == code))
    return result.scalar_one_or_none()


async def use_invite_code(db: AsyncSession, code: str, telegram_id: int) -> bool:
    invite = await get_invite_code(db, code)
    if not invite or not invite.is_active:
        return False
    if invite.uses_count >= invite.max_uses:
        return False
    invite.uses_count += 1
    invite.used_by = telegram_id
    invite.used_at = datetime.utcnow()
    if invite.uses_count >= invite.max_uses:
        invite.is_active = False
    await db.commit()
    return True


async def list_invite_codes(db: AsyncSession) -> list[InviteCode]:
    result = await db.execute(select(InviteCode).order_by(InviteCode.id.desc()))
    return list(result.scalars().all())


# ── CATEGORIES ─────────────────────────────────────────────────────────────────

async def create_category(db: AsyncSession, user_id: int, name: str) -> Category:
    cat = Category(user_id=user_id, name=name)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


async def update_category_topic_id(db: AsyncSession, category_id: int, topic_id: int) -> None:
    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if cat:
        cat.telegram_topic_id = topic_id
        await db.commit()


async def get_categories(db: AsyncSession, user_id: int) -> list[Category]:
    result = await db.execute(
        select(Category).where(Category.user_id == user_id).order_by(Category.name)
    )
    return list(result.scalars().all())


async def get_category(db: AsyncSession, category_id: int, user_id: int) -> Optional[Category]:
    result = await db.execute(
        select(Category).where(and_(Category.id == category_id, Category.user_id == user_id))
    )
    return result.scalar_one_or_none()


async def get_category_idea_count(db: AsyncSession, category_id: int) -> int:
    result = await db.execute(
        select(func.count(Idea.id)).where(Idea.category_id == category_id)
    )
    return result.scalar() or 0


# ── IDEAS ──────────────────────────────────────────────────────────────────────

async def create_idea(
    db: AsyncSession,
    user_id: int,
    category_id: Optional[int],
    content: str,
    ai_summary: Optional[str] = None,
    tags: Optional[list] = None,
) -> Idea:
    idea = Idea(
        user_id=user_id,
        category_id=category_id,
        content=content,
        ai_summary=ai_summary,
        tags=tags or [],
    )
    db.add(idea)
    await db.commit()
    await db.refresh(idea)
    return idea


async def update_idea_message_id(db: AsyncSession, idea_id: int, message_id: int) -> None:
    result = await db.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if idea:
        idea.telegram_message_id = message_id
        await db.commit()


async def get_idea(db: AsyncSession, idea_id: int, user_id: int) -> Optional[Idea]:
    result = await db.execute(
        select(Idea)
        .options(selectinload(Idea.category))
        .where(and_(Idea.id == idea_id, Idea.user_id == user_id))
    )
    return result.scalar_one_or_none()


async def get_ideas_by_category(
    db: AsyncSession,
    category_id: int,
    user_id: int,
    offset: int = 0,
    limit: int = 5,
) -> list[Idea]:
    result = await db.execute(
        select(Idea)
        .where(and_(Idea.category_id == category_id, Idea.user_id == user_id))
        .order_by(Idea.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def count_ideas_in_category(db: AsyncSession, category_id: int, user_id: int) -> int:
    result = await db.execute(
        select(func.count(Idea.id)).where(
            and_(Idea.category_id == category_id, Idea.user_id == user_id)
        )
    )
    return result.scalar() or 0


async def delete_idea(db: AsyncSession, idea_id: int, user_id: int) -> bool:
    idea = await get_idea(db, idea_id, user_id)
    if not idea:
        return False
    await db.delete(idea)
    await db.commit()
    return True


async def get_user_ideas_for_search(db: AsyncSession, user_id: int, limit: int = 150) -> list[Idea]:
    result = await db.execute(
        select(Idea)
        .options(selectinload(Idea.category))
        .where(Idea.user_id == user_id)
        .order_by(Idea.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_all_user_ideas(db: AsyncSession, user_id: int) -> list[Idea]:
    result = await db.execute(
        select(Idea)
        .options(selectinload(Idea.category))
        .where(Idea.user_id == user_id)
        .order_by(Idea.created_at.desc())
    )
    return list(result.scalars().all())


async def get_ideas_for_report(db: AsyncSession, user_id: int, since: datetime) -> list[Idea]:
    result = await db.execute(
        select(Idea)
        .options(selectinload(Idea.category))
        .where(and_(Idea.user_id == user_id, Idea.created_at >= since))
        .order_by(Idea.created_at.desc())
    )
    return list(result.scalars().all())


async def count_inactive_ideas(db: AsyncSession, user_id: int, days: int = 30) -> int:
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(func.count(Idea.id)).where(
            and_(Idea.user_id == user_id, Idea.updated_at < cutoff)
        )
    )
    return result.scalar() or 0


async def get_user_stats(db: AsyncSession, user_id: int) -> dict:
    total_ideas_r = await db.execute(
        select(func.count(Idea.id)).where(Idea.user_id == user_id)
    )
    total_cats_r = await db.execute(
        select(func.count(Category.id)).where(Category.user_id == user_id)
    )
    top_cats_r = await db.execute(
        select(Category.name, func.count(Idea.id).label("cnt"))
        .join(Idea, Idea.category_id == Category.id)
        .where(Category.user_id == user_id)
        .group_by(Category.id, Category.name)
        .order_by(func.count(Idea.id).desc())
        .limit(3)
    )
    last_r = await db.execute(
        select(Idea.created_at)
        .where(Idea.user_id == user_id)
        .order_by(Idea.created_at.desc())
        .limit(1)
    )
    return {
        "total_ideas": total_ideas_r.scalar() or 0,
        "total_categories": total_cats_r.scalar() or 0,
        "top_categories": top_cats_r.fetchall(),
        "last_activity": last_r.scalar_one_or_none(),
    }


# ── REMINDERS ──────────────────────────────────────────────────────────────────

async def get_reminder_config(db: AsyncSession, user_id: int) -> Optional[ReminderConfig]:
    result = await db.execute(
        select(ReminderConfig).where(ReminderConfig.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def upsert_reminder_config(
    db: AsyncSession,
    user_id: int,
    frequency: Optional[str],
    hour: Optional[int],
    day_of_week: Optional[int] = None,
    is_active: bool = True,
) -> ReminderConfig:
    config = await get_reminder_config(db, user_id)
    if config:
        config.frequency = frequency
        config.hour = hour
        config.day_of_week = day_of_week
        config.is_active = is_active
    else:
        config = ReminderConfig(
            user_id=user_id,
            frequency=frequency,
            hour=hour,
            day_of_week=day_of_week,
            is_active=is_active,
        )
        db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def get_active_reminders(db: AsyncSession) -> list[ReminderConfig]:
    result = await db.execute(
        select(ReminderConfig)
        .options(selectinload(ReminderConfig.user))
        .where(ReminderConfig.is_active == True)  # noqa: E712
    )
    return list(result.scalars().all())
