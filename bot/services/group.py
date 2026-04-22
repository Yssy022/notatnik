import os
import logging
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

_GROUP_CHAT_ID_STR = os.getenv("GROUP_CHAT_ID", "0")
GROUP_CHAT_ID = int(_GROUP_CHAT_ID_STR) if _GROUP_CHAT_ID_STR else 0


async def check_group_access(bot: Bot) -> bool:
    if not GROUP_CHAT_ID:
        logger.warning("GROUP_CHAT_ID not set — group features disabled")
        return False
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(GROUP_CHAT_ID, me.id)
        if member.status not in ("administrator", "creator"):
            logger.error("Bot is not an admin in the group")
            return False
        logger.info(f"Group access OK — chat_id={GROUP_CHAT_ID}")
        return True
    except TelegramError as e:
        logger.error(f"Group access check failed: {e}")
        return False


async def create_topic(bot: Bot, category_name: str) -> int | None:
    if not GROUP_CHAT_ID:
        return None
    try:
        topic = await bot.create_forum_topic(chat_id=GROUP_CHAT_ID, name=category_name)
        topic_id = topic.message_thread_id
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=topic_id,
            text=f"📁 Kategoria: *{category_name}* — tutaj będą pojawiać się Twoje pomysły z tej kategorii.",
            parse_mode="Markdown",
        )
        logger.info(f"Created topic '{category_name}' with id={topic_id}")
        return topic_id
    except TelegramError as e:
        logger.error(f"Failed to create topic '{category_name}': {e}")
        return None


async def publish_idea(
    bot: Bot,
    topic_id: int,
    content: str,
    summary: str | None,
    tags: list | None,
    created_at,
) -> int | None:
    if not GROUP_CHAT_ID or not topic_id:
        return None

    tags_str = " ".join(f"#{t}" for t in (tags or []))
    title = content[:60] + ("…" if len(content) > 60 else "")
    date_str = created_at.strftime("%d.%m.%Y %H:%M") if created_at else "-"

    text = (
        f"💡 {title}\n\n"
        f"{content}\n\n"
        f"📝 Podsumowanie: {summary or '-'}\n"
        f"🏷️ Tagi: {tags_str or '-'}\n"
        f"📅 {date_str}"
    )

    try:
        msg = await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=topic_id,
            text=text,
        )
        return msg.message_id
    except TelegramError as e:
        logger.error(f"Failed to publish to topic {topic_id}: {e}")
        return None


def get_idea_deep_link(message_id: int, topic_id: int) -> str | None:
    if not GROUP_CHAT_ID or not message_id or not topic_id:
        return None
    cid = str(GROUP_CHAT_ID)
    if cid.startswith("-100"):
        numeric = cid[4:]
    elif cid.startswith("-"):
        numeric = cid[1:]
    else:
        numeric = cid
    return f"https://t.me/c/{numeric}/{message_id}?thread={topic_id}"
