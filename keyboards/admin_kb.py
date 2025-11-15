from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_panel_kb():
    """Головне меню адмін-панелі."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Адміністратори", callback_data="admins_menu")],
        [InlineKeyboardButton(text="💬 Чати", callback_data="chats_menu")]
    ])

def admins_menu_kb():
    """Меню керування адміністраторами."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати", callback_data="add_admin")],
        [InlineKeyboardButton(text="➖ Видалити", callback_data="remove_admin")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_admin_panel")]
    ])

def choose_plus_time_kb():
    """Клавіатура вибору часу збору '+'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 хв", callback_data="start_global_plus_1"),
            InlineKeyboardButton(text="3 хв", callback_data="start_global_plus_3"),
            InlineKeyboardButton(text="5 хв", callback_data="start_global_plus_5")
        ],
        [
            InlineKeyboardButton(text="15 хв", callback_data="start_global_plus_15"),
            InlineKeyboardButton(text="30 хв", callback_data="start_global_plus_30")
        ],
        [
            InlineKeyboardButton(text="60 хв", callback_data="start_global_plus_60"),
            InlineKeyboardButton(text="90 хв", callback_data="start_global_plus_90"),
            InlineKeyboardButton(text="120 хв", callback_data="start_global_plus_120")
        ]
    ])

