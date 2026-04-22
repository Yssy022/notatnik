import logging
from telegram import Update
from telegram.ext import ContextTypes
from db.database import AsyncSessionLocal
from db.crud import get_user, get_user_ideas_for_search
from bot.services.ai import search_ideas
from bot.services.group import get_idea_deep_link
from bot.keyboards.inline import search_result_keyboard

logger = logging.getLogger(__name__)


async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = " ".join(context.args) if context.args else ""
    if not query_text:
        await update.message.reply_text("Użycie: /find [zapytanie]\nNp: /find pomysły o marketingu")
        return

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        if not db_user or not db_user.is_active:
            await update.message.reply_text("❌ Brak dostępu.")
            return
        await _do_search(update, context, db, db_user, query_text)


async def _do_search(update: Update, context: ContextTypes.DEFAULT_TYPE, db, db_user, query_text: str):
    loading = await update.message.reply_text(f"🔍 Szukam: *{query_text}*…", parse_mode="Markdown")

    ideas = await get_user_ideas_for_search(db, db_user.id)

    if not ideas:
        await loading.edit_text("📭 Nie masz jeszcze żadnych zapisanych pomysłów.")
        return

    ideas_data = [
        {
            "id": i.id,
            "content": i.content[:200],
            "summary": i.ai_summary or "",
            "tags": i.tags or [],
            "category": i.category.name if i.category else "",
        }
        for i in ideas
    ]

    matching_ids = await search_ideas(query_text, ideas_data)

    if not matching_ids:
        await loading.edit_text(
            f"😔 Nie znalazłem nic pasującego do *{query_text}*.\nSpróbuj innych słów kluczowych.",
            parse_mode="Markdown",
        )
        return

    ideas_by_id = {i.id: i for i in ideas}
    found = [ideas_by_id[iid] for iid in matching_ids if iid in ideas_by_id]

    await loading.edit_text(
        f"🔍 Znaleziono *{len(found)}* wyników dla '*{query_text}*':",
        parse_mode="Markdown",
    )

    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    for idx, idea in enumerate(found[:10]):
        emoji = number_emojis[idx] if idx < len(number_emojis) else f"{idx + 1}."
        cat_name = idea.category.name if idea.category else "Brak kategorii"
        date = idea.created_at.strftime("%d.%m.%Y") if idea.created_at else "-"
        preview = idea.content[:60] + ("…" if len(idea.content) > 60 else "")

        group_link = None
        if idea.category and idea.category.telegram_topic_id and idea.telegram_message_id:
            group_link = get_idea_deep_link(idea.telegram_message_id, idea.category.telegram_topic_id)

        await update.message.reply_text(
            f"{emoji} {preview}\n📁 Folder: {cat_name} | 📅 {date}",
            reply_markup=search_result_keyboard(idea.id, group_link),
        )
