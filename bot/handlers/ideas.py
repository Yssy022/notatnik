import logging
import uuid
from collections import defaultdict, deque
import time

from telegram import Update
from telegram.ext import ContextTypes

from db.database import AsyncSessionLocal
from db.crud import (
    get_user, get_categories, get_category, create_category,
    create_idea, get_idea, update_category_topic_id, update_idea_message_id,
)
from bot.services.ai import classify_message, analyze_idea, expand_idea, chat_response
from bot.services import group as group_service
from bot.keyboards.inline import (
    idea_confirmation_keyboard,
    category_select_keyboard,
    expand_idea_keyboard,
)

logger = logging.getLogger(__name__)

# ── RATE LIMITING ─────────────────────────────────────────────────────────────
_rate_buckets: dict[int, deque] = defaultdict(deque)
RATE_MAX = 10
RATE_WINDOW = 60


def _check_rate_limit(user_id: int) -> bool:
    now = time.monotonic()
    bucket = _rate_buckets[user_id]
    while bucket and now - bucket[0] > RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_MAX:
        return False
    bucket.append(now)
    return True


# ── TIMEOUT JOB ───────────────────────────────────────────────────────────────
TIMEOUT_MINUTES = 10


async def _idea_timeout_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    pending_id = job.data["pending_id"]

    user_data = context.application.user_data.get(user_id, {})
    pending = user_data.get("pending_idea")

    if pending and pending.get("id") == pending_id:
        user_data.pop("pending_idea", None)
        user_data.pop("state", None)
        await context.bot.send_message(
            chat_id=chat_id,
            text="⏰ Czas na odpowiedź minął — pomysł nie został zapisany.\nWyślij go ponownie, jeśli chcesz go zapisać.",
        )


def _schedule_timeout(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, pending_id: str):
    context.job_queue.run_once(
        _idea_timeout_callback,
        when=TIMEOUT_MINUTES * 60,
        data={"chat_id": chat_id, "user_id": user_id, "pending_id": pending_id},
        name=f"idea_timeout_{user_id}_{pending_id}",
    )


def _cancel_timeout(context: ContextTypes.DEFAULT_TYPE, user_id: int, pending_id: str):
    for job in context.job_queue.get_jobs_by_name(f"idea_timeout_{user_id}_{pending_id}"):
        job.schedule_removal()


# ── GROUP PUBLISH HELPER ──────────────────────────────────────────────────────
async def _ensure_topic_and_publish(bot, db, cat_id: int, is_new_category: bool, cat_name: str, idea) -> tuple[bool, str | None]:
    """
    Ensures the category has a group topic, then publishes the idea.
    Returns (published: bool, group_link: str | None).
    """
    cat = await get_category(db, cat_id, idea.user_id)
    topic_id = cat.telegram_topic_id if cat else None

    if not topic_id:
        topic_id = await group_service.create_topic(bot, cat_name)
        if topic_id:
            await update_category_topic_id(db, cat_id, topic_id)

    if not topic_id:
        return False, None

    message_id = await group_service.publish_idea(
        bot, topic_id,
        idea.content, idea.ai_summary, idea.tags, idea.created_at,
    )
    if not message_id:
        return False, None

    await update_idea_message_id(db, idea.id, message_id)
    link = group_service.get_idea_deep_link(message_id, topic_id)
    return True, link


# ── MAIN MESSAGE HANDLER ──────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    if not _check_rate_limit(user.id):
        await update.message.reply_text("⚠️ Wysyłasz zbyt wiele wiadomości. Poczekaj chwilę.")
        return

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, user.id)
        if not db_user or not db_user.is_active:
            await update.message.reply_text("❌ Brak dostępu. Użyj /start z kodem zaproszenia.")
            return

        state = context.user_data.get("state")

        if state == "WAITING_NEW_CATEGORY":
            await _handle_new_category_input(update, context, db, db_user, text)
            return

        if state == "WAITING_DELETE_ACCOUNT":
            await _handle_delete_account_confirm(update, context, db, db_user, text)
            return

        loading_msg = await update.message.reply_text("🤔 Analizuję…")
        classification = await classify_message(text)
        msg_type = classification.get("type", "idea")

        if msg_type == "search":
            await loading_msg.delete()
            from bot.handlers.search import _do_search
            await _do_search(update, context, db, db_user, classification.get("query", text))
            return

        if msg_type == "chat":
            response = await chat_response(text)
            await loading_msg.edit_text(response)
            return

        categories = await get_categories(db, db_user.id)
        cat_names = [c.name for c in categories]
        analysis = await analyze_idea(text, cat_names)

        pending_id = str(uuid.uuid4())[:8]
        pending: dict = {
            "id": pending_id,
            "content": text,
            "category": analysis.get("category", "Ogólne"),
            "is_new_category": analysis.get("is_new_category", True),
            "category_id": None,
            "summary": analysis.get("summary", ""),
            "tags": analysis.get("tags", []),
            "db_user_id": db_user.id,
        }

        if not analysis.get("is_new_category"):
            matched = next((c for c in categories if c.name.lower() == analysis["category"].lower()), None)
            if matched:
                pending["category_id"] = matched.id
                pending["is_new_category"] = False

        context.user_data["pending_idea"] = pending
        context.user_data["state"] = "WAITING_CATEGORY_CONFIRM"
        _schedule_timeout(context, update.effective_chat.id, user.id, pending_id)

        tags_str = " ".join(f"#{t}" for t in analysis.get("tags", []))
        new_badge = " *(nowa)*" if pending["is_new_category"] else ""

        await loading_msg.edit_text(
            f"💡 *Twój pomysł został przeanalizowany!*\n\n"
            f"📁 Proponowana kategoria: *{analysis['category']}*{new_badge}\n"
            f"📝 Podsumowanie: {analysis['summary']}\n"
            f"🏷️ Tagi: {tags_str}\n\n"
            f"Czy zgadzasz się z kategorią?",
            parse_mode="Markdown",
            reply_markup=idea_confirmation_keyboard(pending_id),
        )


# ── CALLBACK: CONFIRM SAVE ────────────────────────────────────────────────────
async def cb_idea_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending_id = query.data.split(":")[1]
    pending = context.user_data.get("pending_idea")

    if not pending or pending.get("id") != pending_id:
        await query.edit_message_text("⚠️ Sesja wygasła. Wyślij pomysł ponownie.")
        return

    _cancel_timeout(context, update.effective_user.id, pending_id)

    async with AsyncSessionLocal() as db:
        cat_id = pending.get("category_id")

        if pending.get("is_new_category") and not cat_id:
            new_cat = await create_category(db, pending["db_user_id"], pending["category"])
            cat_id = new_cat.id
            pending["category_id"] = cat_id
            pending["is_new_category"] = False

        idea = await create_idea(
            db,
            user_id=pending["db_user_id"],
            category_id=cat_id,
            content=pending["content"],
            ai_summary=pending["summary"],
            tags=pending["tags"],
        )

        published, group_link = await _ensure_topic_and_publish(
            context.bot, db, cat_id, False, pending["category"], idea
        )

    context.user_data.pop("pending_idea", None)
    context.user_data.pop("state", None)

    tags_str = " ".join(f"#{t}" for t in (pending.get("tags") or []))
    group_note = f"\n🔗 Opublikowano w grupie → kategoria *{pending['category']}*" if published else "\n⚠️ Nie udało się opublikować w grupie (zapisano w bazie)."

    await query.edit_message_text(
        f"✅ *Zapisano!*{group_note}\n\n🏷️ {tags_str}\n\n"
        f"Chcesz żebym rozwinął ten pomysł lub zasugerował kolejne kroki?",
        parse_mode="Markdown",
        reply_markup=expand_idea_keyboard(idea.id, group_link),
    )


# ── CALLBACK: CHANGE CATEGORY ─────────────────────────────────────────────────
async def cb_idea_change_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending_id = query.data.split(":")[1]
    pending = context.user_data.get("pending_idea")

    if not pending or pending.get("id") != pending_id:
        await query.edit_message_text("⚠️ Sesja wygasła. Wyślij pomysł ponownie.")
        return

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        categories = await get_categories(db, db_user.id)

    if not categories:
        await query.answer("Nie masz jeszcze kategorii. Utwórz nową.", show_alert=True)
        return

    await query.edit_message_text(
        "📁 Wybierz kategorię dla swojego pomysłu:",
        reply_markup=category_select_keyboard(categories, pending_id),
    )


# ── CALLBACK: NEW CATEGORY ────────────────────────────────────────────────────
async def cb_idea_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending_id = query.data.split(":")[1]
    pending = context.user_data.get("pending_idea")

    if not pending or pending.get("id") != pending_id:
        await query.edit_message_text("⚠️ Sesja wygasła. Wyślij pomysł ponownie.")
        return

    context.user_data["state"] = "WAITING_NEW_CATEGORY"
    await query.edit_message_text("📁 Podaj nazwę nowej kategorii:")


# ── CALLBACK: SELECT EXISTING CATEGORY ────────────────────────────────────────
async def cb_idea_category_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    pending_id, cat_id = parts[1], int(parts[2])

    pending = context.user_data.get("pending_idea")
    if not pending or pending.get("id") != pending_id:
        await query.edit_message_text("⚠️ Sesja wygasła. Wyślij pomysł ponownie.")
        return

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        cat = await get_category(db, cat_id, db_user.id)

    if not cat:
        await query.answer("❌ Kategoria nie znaleziona.", show_alert=True)
        return

    pending["category_id"] = cat.id
    pending["category"] = cat.name
    pending["is_new_category"] = False

    tags_str = " ".join(f"#{t}" for t in pending.get("tags", []))
    await query.edit_message_text(
        f"💡 *Twój pomysł zostanie zapisany:*\n\n"
        f"📁 Kategoria: *{cat.name}*\n"
        f"📝 Podsumowanie: {pending['summary']}\n"
        f"🏷️ Tagi: {tags_str}\n\n"
        f"Czy zgadzasz się z kategorią?",
        parse_mode="Markdown",
        reply_markup=idea_confirmation_keyboard(pending_id),
    )


# ── CALLBACK: CANCEL ──────────────────────────────────────────────────────────
async def cb_idea_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending_id = query.data.split(":")[1]
    pending = context.user_data.get("pending_idea")
    if pending and pending.get("id") == pending_id:
        _cancel_timeout(context, update.effective_user.id, pending_id)
        context.user_data.pop("pending_idea", None)
        context.user_data.pop("state", None)

    await query.edit_message_text("❌ Anulowano. Pomysł nie został zapisany.")


# ── CALLBACK: EXPAND IDEA ─────────────────────────────────────────────────────
async def cb_expand_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Generuję rozwinięcie…")

    idea_id = int(query.data.split(":")[1])

    async with AsyncSessionLocal() as db:
        db_user = await get_user(db, update.effective_user.id)
        idea = await get_idea(db, idea_id, db_user.id)

    if not idea:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    await query.edit_message_reply_markup(reply_markup=None)
    loading = await context.bot.send_message(query.message.chat_id, "✍️ Generuję rozwinięcie…")
    expansion = await expand_idea(idea.content, idea.ai_summary or "")
    await loading.edit_text(f"💡 *Rozwinięcie pomysłu:*\n\n{expansion}", parse_mode="Markdown")


async def cb_expand_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)


# ── HELPER: new category name input ───────────────────────────────────────────
async def _handle_new_category_input(update, context, db, db_user, text: str):
    name = text.strip()
    if len(name) < 2 or len(name) > 50:
        await update.message.reply_text("❌ Nazwa kategorii musi mieć od 2 do 50 znaków. Spróbuj ponownie:")
        return

    pending = context.user_data.get("pending_idea")
    if not pending:
        context.user_data.pop("state", None)
        await update.message.reply_text("⚠️ Sesja wygasła. Wyślij pomysł ponownie.")
        return

    new_cat = await create_category(db, db_user.id, name)
    topic_id = await group_service.create_topic(context.bot, name)
    if topic_id:
        await update_category_topic_id(db, new_cat.id, topic_id)

    idea = await create_idea(
        db,
        user_id=db_user.id,
        category_id=new_cat.id,
        content=pending["content"],
        ai_summary=pending["summary"],
        tags=pending["tags"],
    )

    published, group_link = False, None
    if topic_id:
        message_id = await group_service.publish_idea(
            context.bot, topic_id, idea.content, idea.ai_summary, idea.tags, idea.created_at
        )
        if message_id:
            await update_idea_message_id(db, idea.id, message_id)
            group_link = group_service.get_idea_deep_link(message_id, topic_id)
            published = True

    _cancel_timeout(context, update.effective_user.id, pending["id"])
    context.user_data.pop("pending_idea", None)
    context.user_data.pop("state", None)

    tags_str = " ".join(f"#{t}" for t in (pending.get("tags") or []))
    group_note = f"\n🔗 Opublikowano w grupie → kategoria *{name}*" if published else "\n⚠️ Nie udało się opublikować w grupie."

    await update.message.reply_text(
        f"✅ *Zapisano w nowej kategorii '{name}'!*{group_note}\n\n🏷️ {tags_str}\n\n"
        f"Chcesz żebym rozwinął ten pomysł lub zasugerował kolejne kroki?",
        parse_mode="Markdown",
        reply_markup=expand_idea_keyboard(idea.id, group_link),
    )


async def _handle_delete_account_confirm(update, context, db, db_user, text: str):
    if text.strip() == "POTWIERDZAM":
        from db.crud import delete_user_all_data
        await delete_user_all_data(db, update.effective_user.id)
        context.user_data.clear()
        await update.message.reply_text("✅ Twoje konto i wszystkie dane zostały usunięte.")
    else:
        context.user_data.pop("state", None)
        await update.message.reply_text("❌ Usuwanie anulowane.")
