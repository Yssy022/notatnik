import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from db.database import AsyncSessionLocal
from db.crud import get_active_reminders, get_ideas_for_report, count_inactive_ideas, get_user_stats

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_bot_app = None


def init_scheduler(app):
    global _bot_app
    _bot_app = app
    scheduler.add_job(check_and_send_reminders, CronTrigger(minute="*"), id="reminder_check", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started")


async def check_and_send_reminders():
    if not _bot_app:
        return

    now = datetime.utcnow()
    current_hour = now.hour
    current_day = now.weekday()  # 0=Monday
    current_minute = now.minute

    if current_minute != 0:
        return

    async with AsyncSessionLocal() as db:
        reminders = await get_active_reminders(db)

    for config in reminders:
        try:
            should_send = False
            if config.frequency == "daily" and config.hour == current_hour:
                should_send = True
            elif (
                config.frequency == "weekly"
                and config.day_of_week == current_day
                and config.hour == current_hour
            ):
                should_send = True

            if should_send:
                await send_report(config.user.telegram_id, config.frequency)
        except Exception as e:
            logger.error(f"Error sending reminder to user {config.user_id}: {e}")


async def send_report(telegram_id: int, frequency: str):
    if not _bot_app:
        return

    period_label = "Dzienny" if frequency == "daily" else "Tygodniowy"
    since = datetime.utcnow() - (timedelta(days=1) if frequency == "daily" else timedelta(days=7))

    async with AsyncSessionLocal() as db:
        from db.crud import get_user
        user = await get_user(db, telegram_id)
        if not user or not user.is_active:
            return

        stats = await get_user_stats(db, user.id)
        new_ideas = await get_ideas_for_report(db, user.id, since)
        inactive_count = await count_inactive_ideas(db, user.id, days=30)

    top_cat = stats["top_categories"][0][0] if stats["top_categories"] else "brak"

    ideas_lines = ""
    for idea in new_ideas[:5]:
        preview = idea.content[:40] + ("…" if len(idea.content) > 40 else "")
        ideas_lines += f"\n• {preview}"

    period_word = "dziś" if frequency == "daily" else "w tym tygodniu"
    text = (
        f"📊 *{period_label} raport pomysłów*\n\n"
        f"📈 Łącznie pomysłów: *{stats['total_ideas']}*\n"
        f"➕ Nowe {period_word}: *{len(new_ideas)}*\n"
        f"📁 Najbardziej aktywna kategoria: *{top_cat}*\n"
    )

    if new_ideas:
        text += f"\n💡 *Nowe pomysły:*{ideas_lines}\n"

    if inactive_count > 0:
        text += f"\n🔔 Masz *{inactive_count}* pomysłów bez aktywności od ponad 30 dni — może czas do nich wrócić?"

    try:
        await _bot_app.bot.send_message(chat_id=telegram_id, text=text, parse_mode="Markdown")
        logger.info(f"Report sent to {telegram_id}")
    except Exception as e:
        logger.error(f"Failed to send report to {telegram_id}: {e}")
