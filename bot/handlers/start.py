import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from db.database import AsyncSessionLocal
from db.crud import get_user, create_user, get_invite_code, use_invite_code

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

HELP_TEXT = """
🤖 *Twój asystent pomysłów*

*Zapisywanie pomysłów:*
Wyślij dowolny tekst — AI go przeanalizuje i zaproponuje kategorię.

*Komendy:*
/folders — przeglądaj kategorie i pomysły
/find [zapytanie] — wyszukaj pomysły
/stats — Twoje statystyki
/remind — skonfiguruj przypomnienia
/export — eksportuj wszystkie pomysły
/delete\_account — usuń konto i dane

*Wskazówka:* Możesz też pisać naturalnie, np.:
• _"Czy mam coś o marketingu?"_
• _"Pokaż pomysły o aplikacjach mobilnych"_
""".strip()

ONBOARDING_TEXT = """
🎉 *Witaj w IdeaBot!*

Jestem Twoim asystentem do zarządzania pomysłami.

📌 *Jak zacząć:*
1. Napisz dowolny pomysł — AI go przeanalizuje i skategoryzuje
2. Przeglądaj swoje pomysły przez /folders
3. Wyszukuj przez /find lub pisząc naturalnie

Wpisz /help żeby zobaczyć wszystkie opcje.

*Zacznij już teraz — napisz swój pierwszy pomysł!* 💡
""".strip()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    async with AsyncSessionLocal() as db:
        existing = await get_user(db, user.id)

        if existing:
            if not existing.is_active:
                await update.message.reply_text("❌ Twoje konto zostało zablokowane. Skontaktuj się z administratorem.")
                return
            await update.message.reply_text("👋 Już jesteś zarejestrowany! Wpisz /help żeby zobaczyć opcje.", parse_mode="Markdown")
            return

        if not args:
            await update.message.reply_text(
                "🔒 Ten bot działa tylko na zaproszenie.\n\nPoproś administratora o link zaproszenia."
            )
            return

        invite_code = args[0].upper()
        invite = await get_invite_code(db, invite_code)

        if not invite or not invite.is_active or invite.uses_count >= invite.max_uses:
            await update.message.reply_text("❌ Kod zaproszenia jest nieprawidłowy lub wygasł.")
            return

        await use_invite_code(db, invite_code, user.id)
        new_user = await create_user(db, user.id, user.username, invite_code)
        logger.info(f"New user registered: {user.id} ({user.username}) via code {invite_code}")

    await update.message.reply_text(ONBOARDING_TEXT, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
    if not db_user or not db_user.is_active:
        await update.message.reply_text("❌ Brak dostępu. Użyj /start z kodem zaproszenia.")
        return
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
