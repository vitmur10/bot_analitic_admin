import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import html
from database.models import Base, User, PollChat, PollResult, PostReaction, ChatMember
from config import TOKEN, admin_only, global_plus_tracking, ALLOWED_USERNAMES
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import StatesGroup, State
from keyboards.main_kb import main_menu
from keyboards.admin_kb import admin_panel_kb, admins_menu_kb, choose_plus_time_kb
from keyboards.poll_kb import back_to_admin_panel_kb, refresh_kb, chats_list_kb, active_plus_kb
from aiogram.types import InlineKeyboardMarkup,InlineKeyboardButton,ChatMemberUpdated
from aiogram.exceptions import TelegramBadRequest
import re
from aiogram.filters import ChatMemberUpdatedFilter, KICKED, LEFT
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter
from aiogram.enums.chat_member_status import ChatMemberStatus
from sqlalchemy.orm import Session as SessionType
# ===================== DATABASE =====================
engine = create_engine("sqlite:///members.db", echo=False)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class AdminStates(StatesGroup):
    waiting_add_admin = State()
    waiting_remove_admin = State()

class CheckReactionsState(StatesGroup):
    waiting_for_link = State()


def normalize_chat_id(chat_id: int | str) -> int:
    """Повертає chat_id у форматі Telegram з префіксом -100 для груп/супергруп."""
    chat_id_str = str(chat_id)
    if chat_id_str.startswith("-100"):
        return int(chat_id_str)
    elif chat_id_str.startswith("-"):
        return int("-100" + chat_id_str[1:])
    else:
        return int("-100" + chat_id_str)


# ===================== ГОЛОВНЕ МЕНЮ =====================

@dp.message(Command("start"))
@admin_only
async def start(message: types.Message):
    if message.chat.type != "private":
        return
    await message.answer("👋 Вітаю в аналітичній панелі!", reply_markup=main_menu())

"""@dp.message(F.new_chat_members)
async def handle_new_members(message: types.Message):
    Додає нових користувачів у базу при вході в чат (без ChatMember).
    session = Session()
    chat_id = normalize_chat_id(message.chat.id)
    chat_title = message.chat.title or f"Chat {chat_id}"

    for member in message.new_chat_members:
        if member.is_bot:
            continue

        # 🔍 Перевіряємо, чи вже є користувач у цьому чаті
        user = session.query(User).filter_by(user_id=member.id, chat_id=chat_id).first()

        if not user:
            # ➕ Додаємо нового
            user = User(
                user_id=member.id,
                chat_id=chat_id,
                full_name=member.full_name,
                username=member.username,
                last_seen=datetime.utcnow()
            )
            session.add(user)
            print(f"🟢 Додано нового користувача: {member.full_name} ({chat_title})")
        else:
            # 🔄 Оновлюємо ім’я/username, якщо змінилися
            user.full_name = member.full_name
            user.username = member.username
            user.last_seen = datetime.utcnow()
            print(f"♻️ Оновлено користувача: {member.full_name} ({chat_title})")

    session.commit()
    session.close()

    # 🔔 Сповіщення у чат
    try:
        joined_users = ", ".join([u.full_name for u in message.new_chat_members if not u.is_bot])
        await message.reply(f"👋 Ласкаво просимо, {joined_users}!")
    except Exception:
        pass"""





# ===================== РЕАКЦІЇ =====================
@dp.message_reaction()
async def on_reaction(event: types.MessageReactionUpdated):
    session = Session()

    # ---- ідентифікатори
    tg_user_id = event.user.id
    chat_id = normalize_chat_id(event.chat.id)
    message_id = event.message_id

    # ---- парсимо емодзі/кастомні емодзі
    reaction_list = []
    if event.new_reaction:
        for r in event.new_reaction:
            if hasattr(r, "emoji") and r.emoji:
                reaction_list.append(r.emoji)
            elif hasattr(r, "custom_emoji_id") and r.custom_emoji_id:
                try:
                    stickers = await bot.get_custom_emoji_stickers([r.custom_emoji_id])
                    if stickers and stickers[0].emoji:
                        reaction_list.append(stickers[0].emoji)
                    else:
                        reaction_list.append(f"[custom:{r.custom_emoji_id}]")
                except Exception:
                    reaction_list.append(f"[custom:{r.custom_emoji_id}]")
            else:
                reaction_list.append("unknown")
    reaction = ", ".join(reaction_list) if reaction_list else "removed"

    # ---- назва чату
    try:
        chat = await bot.get_chat(chat_id)
        chat_title = (chat.title or f"Chat {chat_id}").strip()
    except Exception:
        chat_title = f"Chat {chat_id}"

    # ---- пробуємо дістати короткий текст повідомлення
    message_text = None
    try:
        fwd = await bot.forward_message(tg_user_id, chat_id, message_id)
        if fwd.text or fwd.caption:
            message_text = (fwd.text or fwd.caption).strip()
            if len(message_text) > 40:
                message_text = message_text[:40] + "..."
        await bot.delete_message(tg_user_id, fwd.message_id)
    except Exception:
        message_text = "Без тексту"

    # ---- ШУКАЄМО/СТВОРЮЄМО КОРИСТУВАЧА САМЕ В МЕЖАХ ЦЬОГО ЧАТУ
    user = session.query(User).filter_by(user_id=tg_user_id, chat_id=chat_id).first()
    if not user:
        # якщо в базі немає — додаємо запис для цього чату
        full_name = getattr(event.user, "full_name", None)
        username = getattr(event.user, "username", None)
        user = User(
            user_id=tg_user_id,
            chat_id=chat_id,
            full_name=full_name,
            username=username,
            last_seen=datetime.utcnow()
        )
        session.add(user)
        session.commit()

    # ---- зберігаємо реакцію, ПРИВ’ЯЗАНУ ДО user.id З ЦЬОГО ЧАТУ
    session.add(PostReaction(
        chat_id=chat_id,
        chat_title=chat_title,
        message_id=message_id,
        message_text=message_text or "Без тексту",
        user_id=user.id,                 # <-- внутрішній ID користувача з таблиці User
        reaction=reaction,
        timestamp=datetime.utcnow()
    ))
    session.commit()
    session.close()


# ===================== 👥 УСІ КОРИСТУВАЧІ (з пагінацією) =====================
USERS_PER_PAGE = 20


# 📍 Крок 1. При натисканні "👥 Користувачі" — показуємо список чатів
@dp.message(F.text == "👥 Користувачі")
@admin_only
async def ask_chat_for_users(message: types.Message):
    session = Session()
    chat_ids = session.query(User.chat_id).filter(User.chat_id.isnot(None)).distinct().all()

    chat_titles = {}
    for (chat_id,) in chat_ids:
        chat_id = normalize_chat_id(chat_id)
        title = (
            session.query(func.max(PollChat.chat_title))
            .filter(PollChat.chat_id == chat_id)
            .scalar()
        ) or (
            session.query(func.max(PostReaction.chat_title))
            .filter(PostReaction.chat_id == chat_id)
            .scalar()
        )

        if not title:
            first_user = (
                session.query(User.full_name)
                .filter(User.chat_id == chat_id)
                .first()
            )
            if first_user and first_user[0]:
                title = f"Чат ({first_user[0].split()[0]})"
        chat_titles[chat_id] = title or f"Без назви (ID {chat_id})"

    session.close()
    if not chat_titles:
        await message.answer("❌ У базі ще немає чатів із користувачами.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"users_chat_{chat_id}")]
            for chat_id, title in chat_titles.items()
        ]
    )
    await message.answer("👥 Оберіть чат, користувачів якого показати:", reply_markup=kb)

# 📍 Крок 2. Після вибору чату — показуємо першу сторінку користувачів
@dp.callback_query(F.data.startswith("users_chat_"))
@admin_only
async def show_users_in_chat(callback: types.CallbackQuery):
    chat_id = normalize_chat_id(int(callback.data.split("_")[2]))
    await send_users_page(callback.message.chat.id, 1, chat_id, callback)


# 📍 Крок 3. Пагінація
@dp.callback_query(F.data.startswith("users_page_"))
@admin_only
async def paginate_users(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    page = int(parts[2])
    chat_id = int(parts[3])
    await send_users_page(callback.message.chat.id, page, chat_id=chat_id, callback=callback)


async def send_users_page(chat_id: int, page: int, chat_id_filter: int, callback: types.CallbackQuery = None):
    """Відображає всіх користувачів певного чату (з реальною назвою та нормалізованими даними)."""
    session = Session()

    # 🔹 Отримуємо назву чату з PollChat або PostReaction
    chat_title = (
        session.query(func.max(PollChat.chat_title))
        .filter(PollChat.chat_id == chat_id_filter)
        .scalar()
    ) or (
        session.query(func.max(PostReaction.chat_title))
        .filter(PostReaction.chat_id == chat_id_filter)
        .scalar()
    )

    # Якщо не знайшло — fallback
    chat_title = chat_title or f"Чат {chat_id_filter}"

    # 🔹 Розрахунок користувачів
    total_users = session.query(func.count(User.id)).filter(User.chat_id == chat_id_filter).scalar()
    total_pages = max(1, (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    offset = (page - 1) * USERS_PER_PAGE

    users = (
        session.query(User.full_name, User.username, User.last_seen)
        .filter(User.chat_id == chat_id_filter)
        .order_by(User.full_name.asc())
        .offset(offset)
        .limit(USERS_PER_PAGE)
        .all()
    )

    session.close()

    # 🔹 Якщо немає користувачів
    if not users:
        text = f"❌ У чаті <b>{html.escape(chat_title)}</b> немає користувачів."
    else:
        text = (
            f"👥 <b>Користувачі чату:</b> {html.escape(chat_title)}\n"
            f"📄 Сторінка {page}/{total_pages}\n\n"
        )

        for i, user in enumerate(users, offset + 1):
            name = html.escape(user.full_name or "Без імені")
            username = f" (@{html.escape(user.username)})" if user.username else ""

            # 🔄 Замість last_seen показуємо статус, якщо він давній
            if user.last_seen:
                delta = (datetime.utcnow() - user.last_seen).total_seconds()
                if delta < 60 * 5:
                    status = "🟢 онлайн"
                elif delta < 60 * 60:
                    status = f"🕐 {int(delta // 60)} хв тому"
                else:
                    status = f"⏰ {user.last_seen.strftime('%d.%m.%Y %H:%M')}"
            else:
                status = "невідомо"

            text += f"{i}. {name}{username} — <i>{status}</i>\n"

    # 🔹 Пагінація
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"users_page_{page-1}_{chat_id_filter}"))
    if page < total_pages:
        buttons.append(InlineKeyboardButton("➡️ Вперед", callback_data=f"users_page_{page+1}_{chat_id_filter}"))
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])

    # 🔹 Відображення
    if callback:
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest:
            await callback.answer("✅ Дані вже актуальні")
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)



# ===================== 📊 ОПИТУВАННЯ =====================
@dp.message(F.text == "📊 Опитування")
@admin_only
async def show_polls_menu(message: types.Message):
    session = Session()
    chats = session.query(PollChat.chat_id, PollChat.chat_title).distinct().all()
    session.close()

    if not chats:
        await message.answer("❌ Ще немає зафіксованих опитувань.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c[1] or f"Чат {c[0]}", callback_data=f"chat_{c[0]}")] for c in chats
    ])
    await message.answer("📊 Оберіть чат для перегляду опитувань:", reply_markup=kb)

@dp.message(F.text == "⚙️ Адмін-панель")
@admin_only
async def admin_panel(message: types.Message):
    await message.answer("⚙️ Адмін-панель\nОберіть дію:", reply_markup=admin_panel_kb())


@dp.callback_query(F.data == "chats_menu")
@admin_only
async def show_chats_menu(callback: types.CallbackQuery):
    """Показує всі чати з бази, дозволяє вимикати або вмикати."""
    session = Session()
    chats = (
        session.query(PollChat.chat_id, PollChat.chat_title)
        .distinct()
        .all()
    )
    session.close()

    if not chats:
        await callback.message.edit_text("❌ У базі ще немає жодного чату.")
        return

    await callback.message.edit_text("💬 Список усіх чатів:", reply_markup=chats_list_kb(chats))


@dp.callback_query(F.data.startswith("chat_toggle_"))
@admin_only
async def toggle_chat_status(callback: types.CallbackQuery):
    """Вмикає або вимикає збір даних для конкретного чату."""
    chat_id = int(callback.data.split("_")[2])
    session = Session()

    chats = session.query(PollChat).filter_by(chat_id=chat_id).all()
    if not chats:
        session.close()
        await callback.answer("⚠️ Чат не знайдено у базі.", show_alert=True)
        return

    # Перемикаємо статус
    new_status = not chats[0].active
    for c in chats:
        c.active = new_status
    session.commit()
    session.close()

    status_text = "✅ Активовано" if new_status else "🚫 Вимкнено"
    await callback.answer(f"{status_text} збір даних для цього чату.", show_alert=True)

    # 🔄 Оновлюємо список чатів
    await show_chats_menu(callback)


@dp.callback_query(F.data.startswith("chat_delete_"))
@admin_only
async def delete_chat_handler(callback: types.CallbackQuery):
    chat_id_str = callback.data.replace("chat_delete_", "", 1)

    try:
        chat_id = int(chat_id_str)
    except ValueError:
        await callback.answer("❌ Некоректний ID чату.", show_alert=True)
        return

    session = Session()
    try:
        delete_chat_with_related(session, chat_id)
        session.commit()
    except Exception as e:
        session.rollback()
        # можна залогувати e
        await callback.answer("⚠️ Сталася помилка під час видалення.", show_alert=True)
        session.close()
        return
    finally:
        session.close()

    await callback.answer("✅ Чат та всі пов'язані дані видалено")

    # Оновлюємо список чатів
    session = Session()
    chats = (
        session.query(PollChat.chat_id, PollChat.chat_title)
        .distinct()
        .all()
    )
    session.close()

    if chats:
        await callback.message.edit_text(
            "💬 Список усіх чатів:",
            reply_markup=chats_list_kb(chats)
        )
    else:
        await callback.message.edit_text("❌ У базі більше немає жодного чату.")


@dp.callback_query(F.data == "admins_menu")
@admin_only
async def admins_menu(callback: types.CallbackQuery):
    """Меню керування адміністраторами."""
    # Формуємо текст повідомлення
    if ALLOWED_USERNAMES:
        text = "👑 <b>Керування адміністраторами</b>\n\n"
        text += "Поточні адміністратори:\n"
        for i, name in enumerate(ALLOWED_USERNAMES, 1):
            text += f"{i}. @{name}\n"
    else:
        text = "👑 <b>Керування адміністраторами</b>\n\nПоки що адміністраторів не додано."

    # Редагуємо повідомлення з текстом
    await callback.message.edit_text(text, reply_markup=admins_menu_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "back_to_admin_panel")
@admin_only
async def back_to_admin_panel(callback: types.CallbackQuery):
    """Повернення до головного меню адмін-панелі."""
    await callback.message.edit_text("⚙️ Адмін-панель\nОберіть дію:", reply_markup=back_to_admin_panel_kb())



@dp.callback_query(F.data == "add_admin")
@admin_only
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✏️ Введіть username користувача (без @), щоб додати:")
    await state.set_state(AdminStates.waiting_add_admin)


@dp.message(F.text, AdminStates.waiting_add_admin)
@admin_only
async def add_admin_finish(message: types.Message, state: FSMContext):
    from config import ALLOWED_USERNAMES
    username = message.text.strip().lstrip("@")
    if username.lower() not in [u.lower() for u in ALLOWED_USERNAMES]:
        ALLOWED_USERNAMES.append(username)
        await message.answer(f"✅ @{username} додано до списку адміністраторів.")
    else:
        await message.answer("⚠️ Цей користувач уже є в списку.")
    await state.clear()


@dp.callback_query(F.data == "remove_admin")
@admin_only
async def remove_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🗑 Введіть username користувача (без @), щоб видалити:")
    await state.set_state(AdminStates.waiting_remove_admin)


@dp.message(F.text, AdminStates.waiting_remove_admin)
@admin_only
async def remove_admin_finish(message: types.Message, state: FSMContext):
    from config import ALLOWED_USERNAMES
    username = message.text.strip().lstrip("@")
    if username.lower() in [u.lower() for u in ALLOWED_USERNAMES]:
        ALLOWED_USERNAMES[:] = [u for u in ALLOWED_USERNAMES if u.lower() != username.lower()]
        await message.answer(f"✅ @{username} видалено зі списку адміністраторів.")
    else:
        await message.answer("⚠️ Цього користувача немає у списку.")
    await state.clear()


@dp.callback_query(F.data.startswith("chat_"))
async def list_polls(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[1])
    session = Session()
    polls = session.query(PollChat).filter_by(chat_id=chat_id).all()
    session.close()

    if not polls:
        await callback.message.edit_text("❌ У цьому чаті ще немає опитувань.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p.question[:40] if p.question else f"Опитування {p.poll_id}",
                              callback_data=f"poll_{p.poll_id}")]
        for p in polls
    ])
    chat_title = polls[0].chat_title or f"Чат {chat_id}"
    await callback.message.edit_text(
        f"🗳️ Опитування у чаті <b>{html.escape(chat_title)}</b>:",
        reply_markup=kb, parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("poll_"))
async def poll_analytics(callback: types.CallbackQuery):
    """Показує детальну статистику опитування, враховуючи всіх користувачів цього чату."""
    poll_id = callback.data.split("_", 1)[1]
    session = Session()

    # 🔹 Шукаємо опитування
    poll = session.query(PollChat).filter_by(poll_id=poll_id).first()
    if not poll:
        session.close()
        await callback.answer("⚠️ Опитування не знайдено", show_alert=True)
        return

    # 🔹 Всі результати голосування
    results = session.query(PollResult).filter_by(poll_id=poll_id).all()

    # ✅ Беремо всіх користувачів, які зареєстровані саме в цьому чаті
    users = session.query(User).filter(User.chat_id == poll.chat_id).all()

    # Якщо користувачів немає — виходимо
    if not users:
        session.close()
        await callback.message.edit_text(
            f"❌ У базі немає користувачів для чату <b>{html.escape(poll.chat_title or str(poll.chat_id))}</b>.",
            parse_mode="HTML"
        )
        return

    # 📊 Групуємо голоси за варіантами
    votes_by_option = {}
    for r in results:
        option = r.option_text or "—"
        user = next((u for u in users if u.id == r.user_id), None)
        if not user:
            continue
        name = html.escape(user.full_name or f"ID {user.user_id}")
        username = f" (@{html.escape(user.username)})" if user.username else ""
        votes_by_option.setdefault(option, []).append(f"• {name}{username}")

    # 🔢 Розрахунок
    voted_ids = [r.user_id for r in results]
    non_voted_users = [u for u in users if u.id not in voted_ids]

    total_users = len(users)
    voted_percent = round((len(voted_ids) / total_users) * 100, 1) if total_users else 0
    non_voted_percent = 100 - voted_percent

    # 🧾 Формування тексту
    voted_text = "\n\n".join([
        f"<b>{opt}</b>:\n" + "\n".join(lines[:15]) +
        (f"\n...та ще {len(lines) - 15} користувачів." if len(lines) > 15 else "")
        for opt, lines in votes_by_option.items()
    ]) if votes_by_option else "❌ Ніхто не проголосував."

    non_voted_text = "\n".join([
        f"• {html.escape(u.full_name or 'Без імені')} (@{html.escape(u.username)})"
        if u.username else f"• {html.escape(u.full_name or 'Без імені')}"
        for u in non_voted_users[:20]
    ]) or "✅ Усі вже проголосували."
    if len(non_voted_users) > 20:
        non_voted_text += f"\n...та ще {len(non_voted_users) - 20} користувачів."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Оновити", callback_data=f"refresh_poll_{poll_id}"),
            InlineKeyboardButton(text="🗑️ Видалити", callback_data=f"delete_poll_{poll_id}")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"chat_{poll.chat_id}")]
    ])

    # 🧠 Основний текст
    text = (
        f"🗳️ <b>Опитування:</b> {html.escape(poll.question or 'Без назви')}\n"
        f"💬 <b>Чат:</b> {html.escape(poll.chat_title or str(poll.chat_id))}\n\n"
        f"👥 Усього користувачів у чаті: {total_users}\n"
        f"✅ Проголосували: {len(voted_ids)} ({voted_percent}%)\n"
        f"❌ Не проголосували: {len(non_voted_users)} ({non_voted_percent}%)\n\n"
        f"🧑‍💻 <b>Ті, хто проголосував:</b>\n{voted_text}\n\n"
        f"🚫 <b>Ті, хто ще не проголосував:</b>\n{non_voted_text}"
    )

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    session.close()


@dp.callback_query(F.data.startswith("refresh_poll_"))
async def refresh_poll(callback: types.CallbackQuery):
    """Оновлює статистику конкретного опитування (лише користувачі з відповідного чату)."""
    poll_id = callback.data.split("_", 2)[2]

    session = Session()

    # 🔹 Знаходимо опитування
    poll = session.query(PollChat).filter_by(poll_id=poll_id).first()
    if not poll:
        session.close()
        await callback.answer("⚠️ Опитування не знайдено.", show_alert=True)
        return

    # 🔹 Беремо тільки користувачів із цього чату
    users = session.query(User).filter(User.chat_id == poll.chat_id).all()

    # 🔹 І результати голосування
    results = session.query(PollResult).filter_by(poll_id=poll_id).all()
    session.close()

    # 🧮 Якщо немає користувачів
    if not users:
        await callback.message.edit_text(
            f"❌ У базі немає користувачів для чату <b>{html.escape(poll.chat_title or str(poll.chat_id))}</b>.",
            parse_mode="HTML"
        )
        return

    # 📊 Групуємо голоси за варіантами
    votes_by_option = {}
    for r in results:
        option = r.option_text or "—"
        user = next((u for u in users if u.id == r.user_id), None)
        if not user:
            continue
        name = html.escape(user.full_name or f"ID {user.user_id}")
        username = f" (@{html.escape(user.username)})" if user.username else ""
        votes_by_option.setdefault(option, []).append(f"• {name}{username}")

    # 📈 Підрахунки
    voted_ids = [r.user_id for r in results]
    non_voted_users = [u for u in users if u.id not in voted_ids]

    total_users = len(users)
    voted_percent = round((len(voted_ids) / total_users) * 100, 1) if total_users else 0
    non_voted_percent = 100 - voted_percent

    # 🧾 Формуємо текст
    voted_text = "\n\n".join([
        f"<b>{opt}</b>:\n" + "\n".join(lines[:15]) +
        (f"\n...та ще {len(lines) - 15} користувачів." if len(lines) > 15 else "")
        for opt, lines in votes_by_option.items()
    ]) if votes_by_option else "❌ Ніхто не проголосував."

    non_voted_text = "\n".join([
        f"• {html.escape(u.full_name or 'Без імені')} (@{html.escape(u.username)})"
        if u.username else f"• {html.escape(u.full_name or 'Без імені')}"
        for u in non_voted_users[:20]
    ]) or "✅ Усі вже проголосували."
    if len(non_voted_users) > 20:
        non_voted_text += f"\n...та ще {len(non_voted_users) - 20} користувачів."

    # 🔘 Кнопки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Оновити", callback_data=f"refresh_poll_{poll_id}"),
            InlineKeyboardButton(text="🗑️ Видалити", callback_data=f"delete_poll_{poll_id}")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"chat_{poll.chat_id}")]
    ])

    # 🧠 Формуємо текст
    text = (
        f"🗳️ <b>Опитування:</b> {html.escape(poll.question or 'Без назви')}\n"
        f"💬 <b>Чат:</b> {html.escape(poll.chat_title or str(poll.chat_id))}\n\n"
        f"👥 Усього користувачів у чаті: {total_users}\n"
        f"✅ Проголосували: {len(voted_ids)} ({voted_percent}%)\n"
        f"❌ Не проголосували: {len(non_voted_users)} ({non_voted_percent}%)\n\n"
        f"🧑‍💻 <b>Ті, хто проголосував:</b>\n{voted_text}\n\n"
        f"🚫 <b>Ті, хто ще не проголосував:</b>\n{non_voted_text}"
    )

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("✅ Дані вже актуальні", show_alert=False)
        else:
            raise

@dp.callback_query(F.data.startswith("delete_poll_"))
@admin_only
async def delete_poll(callback: types.CallbackQuery):
    """Видаляє опитування та повʼязані голоси з бази."""
    poll_id = callback.data.split("_")[2]

    session = Session()
    poll = session.query(PollChat).filter_by(poll_id=poll_id).first()
    if not poll:
        session.close()
        await callback.answer("⚠️ Опитування не знайдено.", show_alert=True)
        return

    # 🗑️ Видаляємо всі голоси, повʼязані з цим опитуванням
    deleted_votes = session.query(PollResult).filter_by(poll_id=poll_id).delete()

    # 🗑️ Видаляємо саме опитування
    session.delete(poll)
    session.commit()
    session.close()

    await callback.answer("✅ Опитування видалено з бази!", show_alert=True)

    # 🔄 Повертаємо адміністратора до списку опитувань цього чату
    await callback.message.edit_text(
        f"✅ Опитування <b>{html.escape(poll.question or 'Без назви')}</b> видалено.\n"
        f"🗑️ Видалено також {deleted_votes} голосів.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"chat_{poll.chat_id}")]
        ]),
        parse_mode="HTML"
    )


# ====== ОБРОБКА ПОСИЛАННЯ ======
@dp.message(CheckReactionsState.waiting_for_link)
@admin_only
async def check_reactions_by_link(message: types.Message, state: FSMContext):
    """Отримує посилання і показує аналітику реакцій."""
    url = message.text.strip()

    # 🔍 Перевірка — чи це взагалі схоже на посилання
    if not url.startswith("http") and not url.startswith("t.me"):
        await message.answer("⚠️ Це не схоже на посилання. Виходжу з режиму перевірки реакцій.")
        await state.clear()
        return

    # ✅ Витягуємо chat_id і message_id
    match = re.search(r"t\.me\/(?:c\/)?(\d+)\/(\d+)", url)
    if not match:
        await message.answer("⚠️ Невірний формат посилання. Виходжу з режиму перевірки реакцій.")
        await state.clear()
        return

    raw_chat_id = int(match.group(1))
    msg_id = int(match.group(2))
    chat_id = raw_chat_id if str(raw_chat_id).startswith("-100") else int(f"-100{raw_chat_id}")

    session = Session()

    # 🧩 Беремо тільки реакції з цього чату
    reactions = session.query(PostReaction).filter_by(chat_id=chat_id, message_id=msg_id).all()

    # 👥 І тільки користувачів з цього чату
    users = session.query(User).filter_by(chat_id=chat_id).all()

    # 🧠 Пробуємо знайти назву чату в базі
    chat_title = (
        session.query(func.max(PostReaction.chat_title))
        .filter(PostReaction.chat_id == chat_id)
        .scalar()
    )

    session.close()

    if not reactions:
        await message.answer("❌ Реакцій на це повідомлення не знайдено.")
        await state.clear()
        return

    # 📊 Групуємо реакції
    summary = {}
    reacted_users = []
    for r in reactions:
        summary[r.reaction] = summary.get(r.reaction, 0) + 1
        user = next((u for u in users if u.id == r.user_id), None)
        if user:
            reacted_users.append(f"• {user.full_name or 'Без імені'} — {r.reaction}")

    total = len(reactions)
    summary_text = ", ".join([f"{emoji}: {count}" for emoji, count in summary.items()]) or "—"
    reacted_text = "\n".join(reacted_users[:20]) or "Ніхто не реагував."
    if len(reacted_users) > 20:
        reacted_text += f"\n...та ще {len(reacted_users) - 20} користувачів."

    # 📎 Формуємо посилання на повідомлення
    chat_link_id = str(chat_id).replace("-100", "")
    msg_url = f"https://t.me/c/{chat_link_id}/{msg_id}"

    # 🧩 Використовуємо назву або fallback
    chat_name = html.escape(chat_title) if chat_title else f"Чат {chat_id}"

    text = (
        f"📨 <b>Реакції на повідомлення</b>\n"
        f"💬 <b>Чат:</b> {chat_name}\n"
        f"📎 <a href='{msg_url}'>Перейти до повідомлення</a>\n\n"
        f"❤️ <b>Загалом:</b> {total} реакцій\n"
        f"📊 <b>Статистика:</b> {summary_text}\n\n"
        f"👥 <b>Хто реагував:</b>\n{reacted_text}"
    )

    await message.answer(text, parse_mode="HTML")
    await state.clear()



# ===================== ❤️ АНАЛІТИКА РЕАКЦІЙ =====================
@dp.message(F.text == "📨 Реакції на повідомлення")
@admin_only
async def reactions_menu(message: types.Message, state: FSMContext):
    """Запитує посилання після натискання кнопки."""
    await state.set_state(CheckReactionsState.waiting_for_link)
    await message.answer("📎 Надішліть посилання на повідомлення, щоб перевірити реакції:")


# ===================== АНАЛІТИКА '+' =====================
active_plus_sessions = {}


async def update_reaction_analytics(callback: types.CallbackQuery, chat_id: int, msg_id: int):
    """Оновлює статистику реакцій без створення нового CallbackQuery."""
    session = Session()
    reacted = session.query(PostReaction).filter_by(chat_id=chat_id, message_id=msg_id).all()
    users = session.query(User).all()
    session.close()

    reacted_users = []
    for r in reacted:
        user = next((u for u in users if u.id == r.user_id), None)
        if user:
            reacted_users.append(f"• {user.full_name or 'Без імені'} — {r.reaction}")

    reacted_text = "\n".join(reacted_users[:20]) if reacted_users else "❌ Поки ніхто не реагував."
    if len(reacted_users) > 20:
        reacted_text += f"\n...та ще {len(reacted_users) - 20} користувачів."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оновити", callback_data="refresh_current_view")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"react_chat_{chat_id}")]
    ])

    text = f"❤️ **Аналіз реакцій на повідомлення {msg_id}**\n\n{reacted_text}"

    # Безпечно оновлюємо повідомлення
    from aiogram.exceptions import TelegramBadRequest
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("✅ Дані вже актуальні", show_alert=False)
        else:
            raise


@dp.callback_query(F.data == "refresh_current_view")
async def refresh_reactions(callback: types.CallbackQuery):
    """Оновлення інформації про реакції."""
    import re
    text = callback.message.text or ""

    # Шукаємо ідентифікатор повідомлення
    match = re.search(r"повідомлення (\d+)", text)
    if not match:
        await callback.answer("⚠️ Не вдалося визначити повідомлення для оновлення.", show_alert=True)
        return

    msg_id = int(match.group(1))

    # Знайдемо chat_id з останньої клавіатури
    chat_id = None
    if callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("react_chat_"):
                    chat_id = int(btn.callback_data.split("_")[2])
                    break

    if not chat_id:
        await callback.answer("⚠️ Не знайдено chat_id для оновлення.", show_alert=True)
        return

    # Викликаємо функцію без створення CallbackQuery
    await update_reaction_analytics(callback, chat_id, msg_id)


@dp.callback_query(F.data.startswith("delete_msg_"))
@admin_only
async def delete_message_from_chat(callback: types.CallbackQuery):
    """Видаляє повідомлення з чату та очищає пов’язані реакції з бази."""
    _, _, chat_id, msg_id = callback.data.split("_")
    chat_id, msg_id = int(chat_id), int(msg_id)

    # Видаляємо повідомлення з чату
    try:
        await bot.delete_message(chat_id, msg_id)
        deleted_from_chat = True
    except Exception as e:
        deleted_from_chat = False
        error_msg = str(e)

    # Очищаємо базу
    session = Session()
    deleted_rows = session.query(PostReaction).filter_by(chat_id=chat_id, message_id=msg_id).delete()
    session.commit()
    session.close()

    # Формуємо результат
    if deleted_from_chat:
        text = f"✅ Повідомлення (ID {msg_id}) успішно видалено з чату.\n🗑 Також очищено {deleted_rows} записів реакцій із бази."
        await callback.answer("✅ Видалено успішно!", show_alert=True)
    else:
        text = f"⚠️ Не вдалося видалити повідомлення з чату.\nПричина: {error_msg}\n\n🗑 Проте очищено {deleted_rows} записів реакцій у базі."
        await callback.answer("⚠️ Повідомлення не видалено, але база очищена.", show_alert=True)

    # Оновлюємо повідомлення адміністратора
    await callback.message.edit_text(text)

@dp.message(F.text == "➕ Відстежувати +")
@admin_only
async def choose_plus_chat(message: types.Message):
    """Просить обрати чат для збору '+'."""
    session = Session()

    chats = (
        session.query(User.chat_id)
        .filter(User.chat_id.isnot(None))
        .distinct()
        .all()
    )

    chat_titles = {}
    for (chat_id,) in chats:
        title = (
            session.query(func.max(PollChat.chat_title))
            .filter(PollChat.chat_id == chat_id)
            .scalar()
        ) or (
            session.query(func.max(PostReaction.chat_title))
            .filter(PostReaction.chat_id == chat_id)
            .scalar()
        )
        chat_titles[chat_id] = title or f"Чат {chat_id}"

    session.close()

    if not chat_titles:
        await message.answer("❌ У базі немає жодного чату.")
        return

    # Формуємо клавіатуру для вибору чату
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"plus_chat_{chat_id}")]
            for chat_id, title in chat_titles.items()
        ]
    )

    await message.answer("💬 Оберіть чат, у якому збирати '+':", reply_markup=kb)


# 🧩 КРОК 2 — вибір тривалості після вибору чату
@dp.callback_query(F.data.startswith("plus_chat_"))
@admin_only
async def choose_plus_time(callback: types.CallbackQuery):
    """Після вибору чату пропонує тривалість збору '+'."""
    chat_id = int(callback.data.split("_")[2])
    global_plus_tracking["selected_chat"] = chat_id

    kb = choose_plus_time_kb()  # клавіатура з варіантами 5, 10, 15 хв тощо
    await callback.message.edit_text(
        f"🕒 Оберіть, скільки хвилин збирати '+' у чаті <b>{chat_id}</b>:",
        reply_markup=kb,
        parse_mode="HTML"
    )


# 🧩 КРОК 3 — запуск збору
global_plus_tracking = {}

@dp.callback_query(F.data.startswith("start_global_plus_"))
@admin_only
async def start_global_plus(callback: types.CallbackQuery):
    """Активує збір '+' у вибраному чаті."""
    minutes = int(callback.data.split("_")[-1])
    chat_id = global_plus_tracking.get("selected_chat")

    if not chat_id:
        await callback.answer("⚠️ Спочатку оберіть чат.", show_alert=True)
        return

    try:
        chat = await bot.get_chat(chat_id)
        chat_title = chat.title or f"Чат {chat_id}"
    except Exception:
        chat_title = f"Чат {chat_id}"

    end_time = datetime.utcnow() + timedelta(minutes=minutes)

    # 🧠 окремий трекінг для цього чату
    global_plus_tracking[chat_id] = {
        "active": True,
        "chat_title": chat_title,
        "end_time": end_time,
        "user_ids": set(),
        "initiator_id": callback.from_user.id,
    }

    await callback.message.edit_text(
        f"✅ Збір '+' розпочато у чаті <b>{html.escape(chat_title)}</b>!\n"
        f"🕒 Тривалість: {minutes} хв\n\n"
        f"Після завершення бот надішле підсумковий звіт у ваші особисті повідомлення.",
        reply_markup=active_plus_kb(),
        parse_mode="HTML"
    )

    asyncio.create_task(finish_plus_tracking(chat_id, minutes))

@dp.message()
async def collect_global_plus(message: types.Message):
    """Фіксує '+' лише якщо активний збір у цьому чаті."""
    chat_id = message.chat.id
    text = (message.text or "").strip()

    # DEBUG 1 — будь-яке повідомлення у групі
    #print(f"[DEBUG 1] Отримано повідомлення в чаті {chat_id}: {text}")

    # фільтруємо лише повідомлення з "+"
    if not text.startswith("+"):
        #print("[DEBUG 2] Це не '+', ігнорую.")
        return

    tracking = global_plus_tracking.get(chat_id)
    #print(f"[DEBUG 3] tracking для чату {chat_id}: {tracking}")

    if not tracking:
        #print("[DEBUG 4] ❌ Немає активного збору для цього чату.")
        return

    if not tracking.get("active"):
        #print("[DEBUG 5] ⚠️ Збір у цьому чаті неактивний.")
        return

    now = datetime.utcnow()
    if now > tracking["end_time"]:
        tracking["active"] = False
        #print("[DEBUG 6] ⏰ Час збору закінчився.")
        return

    user_id = message.from_user.id

    session = Session()
    user = session.query(User).filter_by(user_id=user_id, chat_id=chat_id).first()

    if not user:
        user = User(
            user_id=user_id,
            chat_id=chat_id,
            full_name=message.from_user.full_name,
            username=message.from_user.username
        )
        session.add(user)
        session.commit()
        #print(f"[DEBUG 7] ➕ Додано нового користувача {user.full_name}")

    if user.id not in tracking["user_ids"]:
        tracking["user_ids"].add(user.id)
        #print(f"[DEBUG 8] [+] {user.full_name or user.username} додав '+' у чаті {message.chat.title}")

    session.close()


# ===================== ОНОВЛЕННЯ ДАНИХ =====================
@dp.callback_query(F.data == "refresh_plus_data")
@admin_only
async def refresh_plus_data(callback: types.CallbackQuery):
    """Оновлює інформацію про збір '+' для відповідного чату."""
    chat_id = global_plus_tracking.get("selected_chat")
    tracking = global_plus_tracking.get(chat_id)

    if not tracking or not tracking.get("active"):
        await callback.answer("❌ Збір зараз не активний.", show_alert=True)
        return

    chat_title = tracking.get("chat_title", f"Чат {chat_id}")

    session = Session()
    all_users = session.query(User).filter(User.chat_id == chat_id).all()
    plus_user_ids = list(tracking.get("user_ids", []))
    reacted_users = [u for u in all_users if u.id in plus_user_ids]
    not_reacted_users = [u for u in all_users if u.id not in plus_user_ids]
    session.close()

    reacted_text = "\n".join([
        f"• {html.escape(u.full_name or 'Без імені')} (@{html.escape(u.username)})"
        if u.username else f"• {html.escape(u.full_name or 'Без імені')}"
        for u in reacted_users[:20]
    ]) or "❌ Ніхто не поставив '+'"

    not_reacted_text = "\n".join([
        f"• {html.escape(u.full_name or 'Без імені')} (@{html.escape(u.username)})"
        if u.username else f"• {html.escape(u.full_name or 'Без імені')}"
        for u in not_reacted_users[:15]
    ]) or "✅ Усі поставили '+'"

    text = (
        f"📊 <b>Поточний стан збору '+' у чаті:</b> <b>{html.escape(chat_title)}</b>\n\n"
        f"➕ Поставили '+': {len(reacted_users)}\n"
        f"🚫 Не поставили '+': {len(not_reacted_users)}\n\n"
        f"❤️ <b>Ті, хто вже поставив '+':</b>\n{reacted_text}\n\n"
        f"😶 <b>Ще не поставили '+':</b>\n{not_reacted_text}"
    )

    await callback.message.edit_text(text, reply_markup=active_plus_kb(), parse_mode="HTML")

async def send_plus_summary(chat_id: int, tracking: dict, minutes: int):
    """Формує та надсилає звіт про поточний стан збору."""
    chat_title = tracking.get("chat_title", f"Чат {chat_id}")

    session = Session()
    all_users = session.query(User).filter(User.chat_id == chat_id).all()
    plus_user_ids = list(tracking.get("user_ids", []))
    reacted_users = [u for u in all_users if u.id in plus_user_ids]
    not_reacted_users = [u for u in all_users if u.id not in plus_user_ids]
    session.close()

    reacted_text = "\n".join([
        f"• {html.escape(u.full_name or 'Без імені')} (@{html.escape(u.username)})"
        if u.username else f"• {html.escape(u.full_name or 'Без імені')}"
        for u in reacted_users[:20]
    ]) or "❌ Ніхто не поставив '+'"

    not_reacted_text = "\n".join([
        f"• {html.escape(u.full_name or 'Без імені')} (@{html.escape(u.username)})"
        if u.username else f"• {html.escape(u.full_name or 'Без імені')}"
        for u in not_reacted_users[:15]
    ]) or "✅ Усі поставили '+'"

    text = (
        f"📊 <b>Підсумок збору '+' ({minutes} хв)</b>\n"
        f"💬 <b>Чат:</b> {html.escape(chat_title)}\n\n"
        f"➕ Поставили '+': {len(reacted_users)}\n"
        f"🚫 Не поставили '+': {len(not_reacted_users)}\n\n"
        f"❤️ <b>Ті, хто поставив '+':</b>\n{reacted_text}\n\n"
        f"😶 <b>Ті, хто не поставив '+':</b>\n{not_reacted_text}"
    )

    initiator_id = tracking.get("initiator_id")
    if initiator_id:
        try:
            await bot.send_message(initiator_id, text, parse_mode="HTML")
            #print(f"✅ Звіт успішно надіслано адміну ({initiator_id}) для чату {chat_title}")
        except Exception as e:
            print(f"⚠️ Не вдалося надіслати адміну звіт: {e}")
    else:
        print("⚠️ Не знайдено ініціатора збору, звіт не надіслано.")


@dp.callback_query(F.data == "stop_plus_early")
@admin_only
async def stop_plus_early(callback: types.CallbackQuery):
    """Достроково завершує збір '+' і одразу надсилає поточний звіт ініціатору."""
    active_chats = {cid: data for cid, data in global_plus_tracking.items()
                    if isinstance(data, dict) and data.get("active")}

    if not active_chats:
        await callback.answer("⚠️ Збір вже завершено або не активний.", show_alert=True)
        return

    chat_id, tracking = next(iter(active_chats.items()))

    # 🛑 Зупиняємо збір
    tracking["active"] = False
    tracking["stopped_early"] = True  # 🆕 позначаємо, що це дострокове завершення
    await callback.answer("🛑 Збір зупинено достроково.", show_alert=True)

    # 🧠 Одразу формуємо і відправляємо звіт
    await send_plus_summary(chat_id, tracking, 0)


async def finish_plus_tracking(chat_id: int, minutes: int):
    """Завершує відстеження '+' у конкретному чаті (по таймеру)."""
    await asyncio.sleep(minutes * 60)
    tracking = global_plus_tracking.get(chat_id)
    if not tracking:
        #print(f"⚠️ Не знайдено даних для чату {chat_id}")
        return

    # 🧠 Якщо завершено достроково — не дублюємо звіт
    if not tracking.get("active") or tracking.get("stopped_early"):
        #print(f"⏭️ Пропуск звіту — збір у чаті {chat_id} вже завершено достроково.")
        return

    tracking["active"] = False
    await send_plus_summary(chat_id, tracking, minutes)


def delete_chat_with_related(session: SessionType, chat_id: int):
    """Видаляє все, що прив'язане до конкретного chat_id."""

    # Спочатку видаляємо все, що посилається на users (FK user_id),
    # але фільтрується по chat_id
    session.query(PollResult).filter(PollResult.chat_id == chat_id).delete(synchronize_session=False)
    session.query(PostReaction).filter(PostReaction.chat_id == chat_id).delete(synchronize_session=False)
    session.query(ChatMember).filter(ChatMember.chat_id == chat_id).delete(synchronize_session=False)

    # Потім видаляємо користувачів, які були тільки в цьому чаті
    session.query(User).filter(User.chat_id == chat_id).delete(synchronize_session=False)

    # І наостанок сам чат / опитування в цьому чаті
    session.query(PollChat).filter(PollChat.chat_id == chat_id).delete(synchronize_session=False)

@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=(ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)))
async def on_user_left(event: ChatMemberUpdated):
    """Коли користувач виходить — видаляємо його з ChatMember (і, якщо треба, з реакцій/опитувань)."""
    chat_id = event.chat.id
    user_tg_id = event.from_user.id

    session = Session()
    user = session.query(User).filter_by(user_id=user_tg_id, chat_id=chat_id).first()

    if user:
        # 🧹 Видаляємо з ChatMember
        session.query(ChatMember).filter_by(chat_id=chat_id, user_id=user.id).delete()

        # (Не обов’язково, але можна чистити реакції та голоси)
        session.query(PostReaction).filter_by(user_id=user.id, chat_id=chat_id).delete()
        session.query(PollResult).filter_by(user_id=user.id, chat_id=chat_id).delete()

        session.commit()
        #print(f"🗑️ {user.full_name or user.username} видалений з чату {chat_id}")

    session.close()

    # 🔔 Повідомлення в чат
    try:
        await bot.send_message(
            chat_id,
            f"🚪 <b>{event.from_user.full_name}</b> покинув чат.",
            parse_mode="HTML"
        )
    except Exception:
        pass




@dp.message()
async def update_last_seen(message: types.Message):
    """Оновлює час останньої активності користувача в чаті."""
    # Ігноруємо приватні чати, команди та повідомлення без тексту
    if message.chat.type == "private" or not message.text or message.text.startswith("/"):
        return

    session = Session()
    user = session.query(User).filter_by(
        user_id=message.from_user.id,
        chat_id=message.chat.id
    ).first()

    if not user:
        user = User(
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            full_name=message.from_user.full_name,
            username=message.from_user.username,
            last_seen=datetime.utcnow()
        )
        session.add(user)
    else:
        user.last_seen = datetime.utcnow()
        user.full_name = message.from_user.full_name
        user.username = message.from_user.username

    session.commit()
    session.close()


# ===================== ЗАПУСК =====================
async def main():
    print("🚀 AdminBot запущено: опитування, реакції, + та топ-10 активних користувачів.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
