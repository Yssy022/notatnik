from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ── IDEA SAVING FLOW ───────────────────────────────────────────────────────────

def idea_confirmation_keyboard(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tak, zapisz", callback_data=f"ic:{pending_id}"),
            InlineKeyboardButton("✏️ Zmień kategorię", callback_data=f"icc:{pending_id}"),
        ],
        [InlineKeyboardButton("➕ Nowa kategoria", callback_data=f"inc:{pending_id}")],
    ])


def category_select_keyboard(categories: list, pending_id: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(cat.name, callback_data=f"ics:{pending_id}:{cat.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Anuluj", callback_data=f"icancel:{pending_id}")])
    return InlineKeyboardMarkup(buttons)


def expand_idea_keyboard(idea_id: int, group_link: str | None = None) -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton("✅ Tak", callback_data=f"ie:{idea_id}"),
        InlineKeyboardButton("❌ Nie", callback_data=f"ine:{idea_id}"),
    ]]
    if group_link:
        buttons.append([InlineKeyboardButton("🔗 Otwórz w grupie", url=group_link)])
    return InlineKeyboardMarkup(buttons)


# ── FOLDERS ────────────────────────────────────────────────────────────────────

def folder_list_keyboard(categories: list, idea_counts: dict) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for cat in categories:
        count = idea_counts.get(cat.id, 0)
        row.append(InlineKeyboardButton(f"🗂️ {cat.name} ({count})", callback_data=f"fv:{cat.id}:0"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("➕ Nowa kategoria", callback_data="fnewcat")])
    return InlineKeyboardMarkup(buttons)


def folder_ideas_keyboard(
    ideas: list,
    category_id: int,
    page: int,
    total: int,
    page_size: int = 5,
    deep_links: dict | None = None,  # {idea_id: url}
) -> InlineKeyboardMarkup:
    buttons = []
    deep_links = deep_links or {}

    for idea in ideas:
        preview = idea.content[:50] + ("…" if len(idea.content) > 50 else "")
        buttons.append([InlineKeyboardButton(f"💡 {preview}", callback_data=f"iv:{idea.id}")])

        action_row = [
            InlineKeyboardButton("👁️ Pełny", callback_data=f"iv:{idea.id}"),
            InlineKeyboardButton("🗑️ Usuń", callback_data=f"id:{idea.id}"),
        ]
        link = deep_links.get(idea.id)
        if link:
            action_row.insert(1, InlineKeyboardButton("🔗 Skocz do grupy", url=link))
        buttons.append(action_row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Poprzednie", callback_data=f"fv:{category_id}:{page - 1}"))
    if (page + 1) * page_size < total:
        nav_row.append(InlineKeyboardButton("➡️ Następne", callback_data=f"fv:{category_id}:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔙 Powrót do folderów", callback_data="folders_back")])
    return InlineKeyboardMarkup(buttons)


def delete_confirm_keyboard(idea_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tak, usuń", callback_data=f"idc:{idea_id}"),
            InlineKeyboardButton("❌ Anuluj", callback_data=f"idx:{idea_id}"),
        ]
    ])


def back_to_folders_keyboard(group_link: str | None = None) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton("🔙 Powrót do folderów", callback_data="folders_back")]]
    if group_link:
        buttons.insert(0, [InlineKeyboardButton("🔗 Skocz do grupy", url=group_link)])
    return InlineKeyboardMarkup(buttons)


# ── SEARCH RESULTS ─────────────────────────────────────────────────────────────

def search_result_keyboard(idea_id: int, group_link: str | None = None) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton("👁️ Zobacz pełny", callback_data=f"iv:{idea_id}")]]
    if group_link:
        buttons[0].append(InlineKeyboardButton("🔗 Skocz do grupy", url=group_link))
    return InlineKeyboardMarkup(buttons)


# ── REMINDERS ──────────────────────────────────────────────────────────────────

def reminder_frequency_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Codziennie", callback_data="rf:daily"),
            InlineKeyboardButton("📆 Co tydzień", callback_data="rf:weekly"),
        ],
        [InlineKeyboardButton("🔕 Wyłącz", callback_data="rf:off")],
    ])


def reminder_hours_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for h in range(0, 24, 2):
        row.append(InlineKeyboardButton(f"{h:02d}:00", callback_data=f"rh:{h}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def reminder_days_keyboard() -> InlineKeyboardMarkup:
    days = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nie"]
    buttons = []
    row = []
    for i, d in enumerate(days):
        row.append(InlineKeyboardButton(d, callback_data=f"rd:{i}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ── EXPORT ─────────────────────────────────────────────────────────────────────

def export_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📄 TXT", callback_data="ef:txt"),
            InlineKeyboardButton("📋 JSON", callback_data="ef:json"),
        ]
    ])
