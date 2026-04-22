import logging
import logging.handlers
import os
from pathlib import Path

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from db.database import init_db
from bot.handlers.start import cmd_start, cmd_help
from bot.handlers.ideas import (
    handle_message,
    cb_idea_confirm,
    cb_idea_change_category,
    cb_idea_new_category,
    cb_idea_category_select,
    cb_idea_cancel,
    cb_expand_yes,
    cb_expand_no,
)
from bot.handlers.folders import (
    cmd_folders,
    cb_folder_view,
    cb_folders_back,
    cb_idea_view,
    cb_idea_delete_ask,
    cb_idea_delete_confirm,
    cb_idea_delete_cancel,
    cb_folder_new_category,
)
from bot.handlers.search import cmd_find
from bot.handlers.reminders import cmd_remind, cb_reminder_frequency, cb_reminder_day, cb_reminder_hour
from bot.handlers.admin import cmd_gen_invite, cmd_list_invites, cmd_users, cmd_ban, cmd_unban
from bot.handlers.export import cmd_export, cb_export_format, cmd_stats, cmd_delete_account
from bot.services.scheduler import init_scheduler
from bot.services.group import check_group_access


def setup_logging():
    Path("logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.handlers.RotatingFileHandler(
        "logs/bot.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)


async def post_init(application: Application):
    await init_db()
    init_scheduler(application)

    # Check group access
    ok = await check_group_access(application.bot)
    if not ok:
        logging.getLogger(__name__).warning(
            "⚠️  Group access NOT available — ideas will be saved to DB only, group publishing disabled."
        )

    logging.getLogger(__name__).info("Bot initialized")


async def post_shutdown(application: Application):
    from bot.services.scheduler import scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logging.getLogger(__name__).info("Bot shut down cleanly")


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Admin commands
    app.add_handler(CommandHandler("gen_invite", cmd_gen_invite))
    app.add_handler(CommandHandler("list_invites", cmd_list_invites))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))

    # User commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("folders", cmd_folders))
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("remind", cmd_remind))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("delete_account", cmd_delete_account))

    # Idea flow callbacks
    app.add_handler(CallbackQueryHandler(cb_idea_confirm, pattern=r"^ic:"))
    app.add_handler(CallbackQueryHandler(cb_idea_change_category, pattern=r"^icc:"))
    app.add_handler(CallbackQueryHandler(cb_idea_new_category, pattern=r"^inc:"))
    app.add_handler(CallbackQueryHandler(cb_idea_category_select, pattern=r"^ics:"))
    app.add_handler(CallbackQueryHandler(cb_idea_cancel, pattern=r"^icancel:"))
    app.add_handler(CallbackQueryHandler(cb_expand_yes, pattern=r"^ie:"))
    app.add_handler(CallbackQueryHandler(cb_expand_no, pattern=r"^ine:"))

    # Folder callbacks
    app.add_handler(CallbackQueryHandler(cb_folder_view, pattern=r"^fv:"))
    app.add_handler(CallbackQueryHandler(cb_folders_back, pattern=r"^folders_back$"))
    app.add_handler(CallbackQueryHandler(cb_idea_view, pattern=r"^iv:"))
    app.add_handler(CallbackQueryHandler(cb_idea_delete_ask, pattern=r"^id:"))
    app.add_handler(CallbackQueryHandler(cb_idea_delete_confirm, pattern=r"^idc:"))
    app.add_handler(CallbackQueryHandler(cb_idea_delete_cancel, pattern=r"^idx:"))
    app.add_handler(CallbackQueryHandler(cb_folder_new_category, pattern=r"^fnewcat$"))

    # Reminder callbacks
    app.add_handler(CallbackQueryHandler(cb_reminder_frequency, pattern=r"^rf:"))
    app.add_handler(CallbackQueryHandler(cb_reminder_day, pattern=r"^rd:"))
    app.add_handler(CallbackQueryHandler(cb_reminder_hour, pattern=r"^rh:"))

    # Export callback
    app.add_handler(CallbackQueryHandler(cb_export_format, pattern=r"^ef:"))

    # Catch-all text handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting bot…")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
