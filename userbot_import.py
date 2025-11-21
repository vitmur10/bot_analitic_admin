import asyncio
from datetime import datetime
from telethon import TelegramClient, events, functions
from telethon.tl.types import MessageMediaPoll
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import User, Base, PollChat, PollResult
import traceback
from telethon.errors import RPCError
from config import API_ID, API_HASH, NAME
# ================== CONFIG ==================


engine = create_engine("sqlite:///members.db", echo=False)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

client = TelegramClient(NAME, API_ID, API_HASH)

# ==========================================================
def normalize_chat_id(chat_id: int) -> int:
    """Повертає chat_id у Telegram-форматі з префіксом -100."""
    return chat_id if str(chat_id).startswith("-100") else int(f"-100{chat_id}")


async def import_members_to_db(group):
    """Імпортує всіх учасників конкретного чату (group) у таблицю User."""
    session = Session()

    # Отримуємо chat_id у правильному форматі
    chat_id = normalize_chat_id(group.id)
    chat_title = getattr(group, "title", f"Chat {chat_id}")

    # Отримуємо список учасників
    participants = await client.get_participants(group)
    count = 0

    for user in participants:
        if getattr(user, "bot", False):
            continue  # пропускаємо ботів

        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

        # Перевіряємо, чи користувач уже є в цьому чаті
        db_user = session.query(User).filter_by(user_id=user.id, chat_id=chat_id).first()

        if not db_user:
            db_user = User(
                user_id=user.id,
                chat_id=chat_id,
                username=user.username,
                full_name=full_name,
                last_seen=datetime.utcnow()
            )
            session.add(db_user)
            #print(f"🟢 Додано {full_name} (@{user.username}) у {chat_title}")
        else:
            db_user.username = user.username
            db_user.full_name = full_name
            db_user.last_seen = datetime.utcnow()
            #print(f"♻️ Оновлено {full_name} (@{user.username}) у {chat_title}")

        count += 1

    session.commit()
    session.close()

    #print(f"✅ Імпорт завершено: {count} користувачів з {chat_title}")



@client.on(events.NewMessage(pattern=r"^/sync_members$"))
async def sync_handler(event):
    """Ручна команда для оновлення списку учасників"""
    chat = await event.get_chat()
    await event.reply("🔄 Оновлюю список учасників...")
    await import_members_to_db(chat)
    await event.reply("✅ Готово! Учасників оновлено.")


# ==========================================================
@client.on(events.NewMessage)
async def detect_polls(event):
    """Фіксує нові опитування та голосує автоматично."""
    if not event.media or not isinstance(event.media, MessageMediaPoll):
        return

    poll = event.media.poll
    chat = await event.get_chat()
    session = Session()

    # нормалізуємо chat_id
    chat_id = normalize_chat_id(event.chat_id)

    # Перевіряємо, чи опитування вже збережено
    existing = session.query(PollChat).filter_by(chat_id=chat_id, poll_id=str(poll.id)).first()
    if existing:
        session.close()
        return

    question_text = getattr(poll.question, "text", str(poll.question))

    session.add(PollChat(
        poll_id=str(poll.id),
        chat_id=chat_id,
        chat_title=getattr(chat, "title", None),
        question=question_text,
        author_id=event.sender_id,
        message_id=event.id
    ))

    session.commit()
    session.close()

    # --- Автоматичне голосування ---
    try:
        # ВАРІАНТ 1 — проголосувати за перший варіант:
        await event.message.click(0)
        print(f"✅ Проголосовано за перший варіант опитування в чаті {chat_id}: {question_text}")

        # --- АБО: випадковий варіант (щоб виглядало "живіше")
        # index = random.randrange(len(poll.options))
        # await event.message.click(index)
        # print(f"✅ Проголосовано за варіант {index} (випадковий) у чаті {chat_id}: {question_text}")

    except RPCError as e:
        # Помилки RPC — покажемо їх
        print(f"❌ Не вдалося проголосувати (RPCError): {e}")

        # Якщо ваша версія Telethon старіша і не підтримує click() для опитувань,
        # запропонуємо оновити Telethon (але не намагаємось вгадувати байти опцій тут).
        print("ℹ️ Якщо проблема через версію Telethon, спробуйте оновити бібліотеку: pip install -U telethon")

    except Exception as e:
        # Загальна обробка помилок
        print(f"❌ Не вдалося проголосувати: {e}")


# ==========================================================
async def check_poll_votes(interval=10):
    """Регулярно перевіряє результати опитувань і зберігає текст обраного варіанту."""
    await asyncio.sleep(5)
    while True:
        session = Session()
        polls = session.query(PollChat).all()

        for p in polls:
            try:
                chat_id = normalize_chat_id(p.chat_id)

                # 🔄 якщо у PollChat старий формат chat_id — оновлюємо
                if p.chat_id != chat_id:
                    p.chat_id = chat_id
                    session.commit()

                msg = await client.get_messages(chat_id, ids=p.message_id)
                if not msg or not msg.media or not isinstance(msg.media, MessageMediaPoll):
                    continue

                poll = msg.media.poll
                results = msg.media.results
                if not results or not getattr(results, "results", None):
                    continue

                options = poll.answers
                if not options:
                    continue

                # 🧹 очищаємо старі результати для цього опитування
                session.query(PollResult).filter_by(poll_id=p.poll_id).delete()
                session.commit()

                for option in options:
                    try:
                        option_text = str(option.text.text if hasattr(option.text, "text") else option.text).strip() or "—"

                        votes = await client(functions.messages.GetPollVotesRequest(
                            peer=await client.get_input_entity(chat_id),
                            id=msg.id,
                            option=option.option,
                            limit=100
                        ))

                        voter_list = getattr(votes, "voters", getattr(votes, "users", []))

                        for voter in voter_list:
                            user_tg_id = getattr(voter, "user_id", getattr(voter, "id", None))
                            if not user_tg_id:
                                continue

                            # 🔍 шукаємо користувача саме у цьому чаті
                            user = session.query(User).filter_by(user_id=user_tg_id, chat_id=chat_id).first()

                            # ➕ якщо немає — додаємо нового користувача
                            if not user:
                                try:
                                    entity = await client.get_entity(user_tg_id)
                                    username = entity.username
                                    full_name = f"{entity.first_name or ''} {entity.last_name or ''}".strip()

                                    user = User(
                                        user_id=user_tg_id,
                                        chat_id=chat_id,
                                        username=username,
                                        full_name=full_name,
                                    )
                                    session.add(user)
                                    session.commit()

                                    print(f"👤 Новий користувач у чаті {chat_id}: {full_name}")

                                except Exception as e:
                                    print(f"⚠️ Не вдалося отримати entity для user_id={user_tg_id}: {e}")
                                    continue

                            # 💾 зберігаємо результат, зв’язуючи з конкретним user.id
                            result = PollResult(
                                poll_id=p.poll_id,
                                chat_id=chat_id,
                                user_id=user.id,  # внутрішній ID із таблиці User
                                option_text=option_text,
                                timestamp=datetime.utcnow()
                            )
                            session.add(result)
                            session.commit()

                        #print(f"📊 '{poll.question}' — '{option_text}': {len(voter_list)} голосів")

                    except Exception as e:
                        if "Cast a vote" in str(e):
                            print(f"🚫 '{poll.question}' — бот не може отримати голоси (не голосував).")
                        elif "'VotesList' object" in str(e):
                            print(f"⚠️ '{poll.question}' — структура VotesList без users, пропускаю.")
                        else:
                            print(f"⚠️ Помилка '{poll.question}': {e}")

            except Exception:
                print(f"⚠️ Глобальна помилка для '{p.poll_id}': {traceback.format_exc()}")

        session.close()
        await asyncio.sleep(interval)



# ==========================================================
async def main():
    print("🚀 UserBot запущено.")
    print("🔹 /sync_members — оновити учасників")
    print("🔹 Опитування зберігаються автоматично")
    print("🔹 Кожні 10 секунд оновлюються результати голосів")

    await client.start()
    asyncio.create_task(check_poll_votes(10))
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())