import logging
from telegram import Update
from telegram.ext import ContextTypes
from db.database import AsyncSessionLocal
from db.crud import (
    get_user, get_categories, get_category_idea_count,
    get_ideas_by_category, count_ideas_in_category, get_idea, delete_idea, get_category,
)
from bot.services.group import get_idea_deep_link
from bot.keyboards.inline import (
    folder_list_keyboard, folder_ideas_keyboard,
    delete_confirm_keyboard, back_to_folders_keyboard,
)

logger = logging.getLogger(__name__)
PAGE_SIZE = 5


async def cmd_folders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        if not db_user or not db_user.is_active:
            await update.message.reply_text("❌ Brak dostępu.")
            return

        categories = await get_categories(db, db_user.id)
        if not categories:
            await update.message.reply_text(
                "📁 Nie masz jeszcze żadnych kategorii.\nWyślij swój pierwszy pomysł — AI automatycznie go skategoryzuje!"
            )
            return

        idea_counts = {cat.id: await get_category_idea_count(db, cat.id) for cat in categories}

    await update.message.reply_text(
        f"📁 *Twoje foldery* ({len(categories)}):",
        parse_mode="Markdown",
        reply_markup=folder_list_keyboard(categories, idea_counts),
    )


async def cb_folder_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    cat_id, page = int(parts[1]), int(parts[2])
    offset = page * PAGE_SIZE

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        if not db_user:
            return

        cat = await get_category(db, cat_id, db_user.id)
        if not cat:
            await query.answer("❌ Kategoria nie znaleziona.", show_alert=True)
            return

        ideas = await get_ideas_by_category(db, cat_id, db_user.id, offset=offset, limit=PAGE_SIZE)
        total = await count_ideas_in_category(db, cat_id, db_user.id)

        # Build deep links for ideas that have group message
        deep_links = {}
        if cat.telegram_topic_id:
            for idea in ideas:
                if idea.telegram_message_id:
                    link = get_idea_deep_link(idea.telegram_message_id, cat.telegram_topic_id)
                    if link:
                        deep_links[idea.id] = link

    if not ideas:
        await query.edit_message_text(
            f"📁 *{cat.name}* — brak pomysłów",
            parse_mode="Markdown",
            reply_markup=back_to_folders_keyboard(),
        )
        return

    lines = [f"📁 *{cat.name}* — {total} pomysłów (strona {page + 1}):\n"]
    for idea in ideas:
        preview = idea.content[:50] + ("…" if len(idea.content) > 50 else "")
        date = idea.created_at.strftime("%d.%m.%Y") if idea.created_at else "-"
        tags_str = " ".join(f"#{t}" for t in (idea.tags or [])[:3])
        lines.append(f"💡 {preview}\n📅 {date} | 🏷️ {tags_str}")

    await query.edit_message_text(
        "\n\n".join(lines),
        parse_mode="Markdown",
        reply_markup=folder_ideas_keyboard(ideas, cat_id, page, total, PAGE_SIZE, deep_links),
    )


async def cb_folders_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        if not db_user:
            return
        categories = await get_categories(db, db_user.id)
        idea_counts = {cat.id: await get_category_idea_count(db, cat.id) for cat in categories}

    if not categories:
        await query.edit_message_text("📁 Brak folderów.")
        return

    await query.edit_message_text(
        f"📁 *Twoje foldery* ({len(categories)}):",
        parse_mode="Markdown",
        reply_markup=folder_list_keyboard(categories, idea_counts),
    )


async def cb_idea_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idea_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        idea = await get_idea(db, idea_id, db_user.id)

    if not idea:
        await query.answer("❌ Pomysł nie znaleziony.", show_alert=True)
        return

    cat_name = idea.category.name if idea.category else "Brak kategorii"
    tags_str = " ".join(f"#{t}" for t in (idea.tags or []))
    date = idea.created_at.strftime("%d.%m.%Y %H:%M") if idea.created_at else "-"

    group_link = None
    if idea.category and idea.category.telegram_topic_id and idea.telegram_message_id:
        group_link = get_idea_deep_link(idea.telegram_message_id, idea.category.telegram_topic_id)

    text = (
        f"💡 *Pomysł #{idea.id}*\n\n"
        f"{idea.content}\n\n"
        f"📝 *Podsumowanie:* {idea.ai_summary or '-'}\n"
        f"📁 *Kategoria:* {cat_name}\n"
        f"🏷️ *Tagi:* {tags_str or '-'}\n"
        f"📅 *Data:* {date}"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=back_to_folders_keyboard(group_link),
    )


async def cb_idea_delete_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idea_id = int(query.data.split(":")[1])
    await query.edit_message_text(
        "🗑️ Czy na pewno chcesz usunąć ten pomysł?",
        reply_markup=delete_confirm_keyboard(idea_id),
    )


async def cb_idea_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idea_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        ok = await delete_idea(db, idea_id, db_user.id)

    await query.edit_message_text("✅ Pomysł został usunięty." if ok else "❌ Nie udało się usunąć.")


async def cb_idea_delete_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Anulowano. Pomysł pozostaje zapisany.")


async def cb_folder_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["state"] = "WAITING_NEW_CATEGORY_STANDALONE"
    await query.edit_message_text("📁 Podaj nazwę nowej kategorii:")
