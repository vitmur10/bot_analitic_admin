from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def back_to_admin_panel_kb():
    """Клавіатура для повернення в адмін-панель."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Адміністратори", callback_data="admins_menu")],
        [InlineKeyboardButton(text="💬 Чати", callback_data="chats_menu")]
    ])

def reaction_analytics_kb(chat_id: int, msg_id: int):
    """Клавіатура для аналітики реакцій."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Видалити повідомлення", callback_data=f"delete_msg_{chat_id}_{msg_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"react_chat_{chat_id}")]
    ])

def chats_list_kb(chats):
    """Список чатів."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{c[1] or 'Без назви'}",
                    callback_data=f"chat_toggle_{c[0]}"
                ),
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"chat_delete_{c[0]}"
                ),
            ]
            for c in chats
        ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]]
    )


def active_plus_kb():
    """Клавіатура для активного збору '+'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Оновити", callback_data="refresh_plus_data"),
            InlineKeyboardButton(text="🛑 Завершити", callback_data="stop_plus_early")
        ]
    ])

def refresh_kb(callback_data_back: str):
    """Клавіатура з кнопкою оновлення та повернення."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Оновити", callback_data="refresh_current_view"),
            InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data_back)
        ]
    ])