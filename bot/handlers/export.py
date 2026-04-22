import json
import io
import logging
from datetime import datetime
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from db.database import AsyncSessionLocal
from db.crud import get_user, get_all_user_ideas, get_user_stats
from bot.keyboards.inline import export_format_keyboard

logger = logging.getLogger(__name__)


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        if not db_user or not db_user.is_active:
            await update.message.reply_text("❌ Brak dostępu.")
            return

    await update.message.reply_text(
        "📤 *Eksport danych*\nWybierz format pliku:",
        parse_mode="Markdown",
        reply_markup=export_format_keyboard(),
    )


async def cb_export_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Generuję plik…")

    fmt = query.data.split(":")[1]

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        ideas = await get_all_user_ideas(db, db_user.id)

    if not ideas:
        await query.edit_message_text("📭 Nie masz jeszcze żadnych pomysłów do eksportu.")
        return

    await query.edit_message_text(f"⏳ Generuję plik {fmt.upper()}…")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"pomysly_{timestamp}.{fmt}"

    if fmt == "json":
        data = [
            {
                "id": i.id,
                "content": i.content,
                "summary": i.ai_summary,
                "tags": i.tags or [],
                "category": i.category.name if i.category else None,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in ideas
        ]
        file_content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    else:  # txt
        lines = [f"EKSPORT POMYSŁÓW — {datetime.now().strftime('%d.%m.%Y %H:%M')}", "=" * 50, ""]
        for idea in ideas:
            cat = idea.category.name if idea.category else "Brak kategorii"
            date = idea.created_at.strftime("%d.%m.%Y") if idea.created_at else "-"
            tags = " ".join(f"#{t}" for t in (idea.tags or []))
            lines += [
                f"ID: {idea.id}",
                f"Data: {date}",
                f"Kategoria: {cat}",
                f"Tagi: {tags}",
                f"Treść:\n{idea.content}",
                f"Podsumowanie: {idea.ai_summary or '-'}",
                "-" * 40,
                "",
            ]
        file_content = "\n".join(lines).encode("utf-8")

    file_obj = io.BytesIO(file_content)
    file_obj.name = filename

    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=InputFile(file_obj, filename=filename),
        caption=f"✅ Eksport gotowy! {len(ideas)} pomysłów.",
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        if not db_user or not db_user.is_active:
            await update.message.reply_text("❌ Brak dostępu.")
            return
        stats = await get_user_stats(db, db_user.id)

    joined = db_user.created_at.strftime("%d.%m.%Y") if db_user.created_at else "-"
    last_active = stats["last_activity"].strftime("%d.%m.%Y") if stats["last_activity"] else "brak aktywności"

    top_cats = ""
    for i, (name, count) in enumerate(stats["top_categories"], 1):
        top_cats += f"\n  {i}. {name} ({count} pomysłów)"

    text = (
        f"📊 *Twoje statystyki*\n\n"
        f"💡 Łącznie pomysłów: *{stats['total_ideas']}*\n"
        f"📁 Liczba kategorii: *{stats['total_categories']}*\n"
        f"📅 Data dołączenia: {joined}\n"
        f"🕐 Ostatnia aktywność: {last_active}\n"
    )
    if top_cats:
        text += f"\n🏆 *Top kategorie:*{top_cats}"

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        if not db_user or not db_user.is_active:
            await update.message.reply_text("❌ Brak dostępu.")
            return

    context.user_data["state"] = "WAITING_DELETE_ACCOUNT"
    await update.message.reply_text(
        "⚠️ *Usunięcie konta*\n\n"
        "Ta operacja jest nieodwracalna!\nUsunięte zostaną:\n"
        "• Wszystkie Twoje pomysły\n"
        "• Wszystkie kategorie\n"
        "• Konfiguracja przypomnień\n\n"
        "Aby potwierdzić, wpisz dokładnie: `POTWIERDZAM`\n"
        "Aby anulować — wyślij cokolwiek innego.",
        parse_mode="Markdown",
    )
