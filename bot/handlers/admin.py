import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from db.database import AsyncSessionLocal
from db.crud import (
    create_invite_code, list_invite_codes, get_all_users,
    ban_user, unban_user, get_user,
)

logger = logging.getLogger(__name__)
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Brak uprawnień.")
            return
        return await func(update, context)
    return wrapper


@admin_only
async def cmd_gen_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    max_uses = 1
    if context.args:
        try:
            max_uses = int(context.args[0])
            if max_uses < 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Podaj prawidłową liczbę użyć, np. /gen_invite 5")
            return

    async with AsyncSessionLocal() as db:
        invite = await create_invite_code(db, update.effective_user.id, max_uses)

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={invite.code}"

    text = (
        f"✅ *Nowy kod zaproszenia:*\n\n"
        f"`{invite.code}`\n\n"
        f"🔗 Link: {link}\n\n"
        f"🔁 Maks. użyć: {max_uses}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


@admin_only
async def cmd_list_invites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as db:
        invites = await list_invite_codes(db)

    if not invites:
        await update.message.reply_text("Brak kodów zaproszeń.")
        return

    lines = ["📋 *Lista kodów zaproszeń:*\n"]
    for inv in invites:
        status = "✅" if inv.is_active else "❌"
        lines.append(
            f"{status} `{inv.code}` — {inv.uses_count}/{inv.max_uses} użyć"
            + (f" | ostatnio użyty przez: {inv.used_by}" if inv.used_by else "")
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as db:
        users = await get_all_users(db)

    if not users:
        await update.message.reply_text("Brak zarejestrowanych użytkowników.")
        return

    lines = [f"👥 *Zarejestrowani użytkownicy ({len(users)}):*\n"]
    for u in users[:50]:
        status = "✅" if u.is_active else "🚫"
        uname = f"@{u.username}" if u.username else "brak username"
        date = u.created_at.strftime("%d.%m.%Y") if u.created_at else "-"
        lines.append(f"{status} `{u.telegram_id}` {uname} — dołączył {date}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@admin_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Użycie: /ban [telegram_id]")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Nieprawidłowe ID.")
        return

    async with AsyncSessionLocal() as db:
        ok = await ban_user(db, tid)

    if ok:
        await update.message.reply_text(f"🚫 Użytkownik `{tid}` zablokowany.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Nie znaleziono użytkownika.")


@admin_only
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Użycie: /unban [telegram_id]")
        return
    try:
        tid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Nieprawidłowe ID.")
        return

    async with AsyncSessionLocal() as db:
        ok = await unban_user(db, tid)

    if ok:
        await update.message.reply_text(f"✅ Użytkownik `{tid}` odblokowany.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Nie znaleziono użytkownika.")
