from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu():
    """Головне меню з основними діями."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Опитування"), KeyboardButton(text="📨 Реакції на повідомлення")],
            [KeyboardButton(text="👥 Користувачі"), KeyboardButton(text="⚙️ Адмін-панель")],
            [KeyboardButton(text="➕ Відстежувати +")],

        ],
        resize_keyboard=True,
        input_field_placeholder="Оберіть дію нижче 👇"
    )



