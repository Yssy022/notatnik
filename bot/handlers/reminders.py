import logging
from telegram import Update
from telegram.ext import ContextTypes
from db.database import AsyncSessionLocal
from db.crud import get_user, upsert_reminder_config, get_reminder_config
from bot.keyboards.inline import reminder_frequency_keyboard, reminder_hours_keyboard, reminder_days_keyboard

logger = logging.getLogger(__name__)

DAYS_PL = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]


async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        if not db_user or not db_user.is_active:
            await update.message.reply_text("❌ Brak dostępu.")
            return
        config = await get_reminder_config(db, db_user.id)

    status = "wyłączone"
    if config and config.is_active:
        if config.frequency == "daily":
            status = f"codziennie o {config.hour:02d}:00"
        elif config.frequency == "weekly":
            day = DAYS_PL[config.day_of_week] if config.day_of_week is not None else "?"
            status = f"co tydzień w {day} o {config.hour:02d}:00"

    await update.message.reply_text(
        f"🔔 *Przypomnienia i raporty*\nAktualny status: {status}\n\nWybierz częstotliwość:",
        parse_mode="Markdown",
        reply_markup=reminder_frequency_keyboard(),
    )


async def cb_reminder_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    freq = query.data.split(":")[1]

    if freq == "off":
        async with AsyncSessionLocal() as db:
            db_user = await get_user(db, update.effective_user.id)
            await upsert_reminder_config(db, db_user.id, None, None, None, is_active=False)
        await query.edit_message_text("🔕 Przypomnienia zostały wyłączone.")
        return

    context.user_data["reminder_freq"] = freq

    if freq == "daily":
        await query.edit_message_text(
            "🕐 Wybierz godzinę wysyłania raportu:",
            reply_markup=reminder_hours_keyboard(),
        )
    elif freq == "weekly":
        await query.edit_message_text(
            "📅 Wybierz dzień tygodnia:",
            reply_markup=reminder_days_keyboard(),
        )


async def cb_reminder_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    day = int(query.data.split(":")[1])
    context.user_data["reminder_day"] = day

    await query.edit_message_text(
        f"🕐 Wybierz godzinę wysyłania raportu ({DAYS_PL[day]}):",
        reply_markup=reminder_hours_keyboard(),
    )


async def cb_reminder_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    hour = int(query.data.split(":")[1])
    freq = context.user_data.get("reminder_freq", "daily")
    day = context.user_data.get("reminder_day")

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        await upsert_reminder_config(db, db_user.id, freq, hour, day, is_active=True)

    context.user_data.pop("reminder_freq", None)
    context.user_data.pop("reminder_day", None)

    if freq == "daily":
        summary = f"codziennie o {hour:02d}:00"
    else:
        day_name = DAYS_PL[day] if day is not None else "?"
        summary = f"co tydzień w {day_name} o {hour:02d}:00"

    await query.edit_message_text(
        f"✅ Przypomnienia ustawione!\n📅 Raport będzie wysyłany: *{summary}*",
        parse_mode="Markdown",
    )
