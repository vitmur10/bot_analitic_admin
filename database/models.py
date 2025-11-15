from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


# 👤 Таблиця користувачів
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=False)  # ⚠️ не робимо global unique, бо користувач може бути в різних чатах
    chat_id = Column(Integer, index=True)  # 🆕 нове поле
    username = Column(String)
    full_name = Column(String)
    last_seen = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.full_name or self.username} ({self.chat_id})>"


# 🗳️ Таблиця опитувань
class PollChat(Base):
    __tablename__ = "poll_chat_map"

    id = Column(Integer, primary_key=True)
    poll_id = Column(String)  # ❌ видаляємо unique=True
    chat_id = Column(Integer)
    chat_title = Column(String, nullable=True)
    message_id = Column(Integer)
    question = Column(String)
    author_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_closed = Column(Boolean, default=False)
    active = Column(Boolean, default=True)


# ✅ Таблиця результатів опитувань (хто що вибрав)
class PollResult(Base):
    __tablename__ = "poll_results"

    id = Column(Integer, primary_key=True)
    poll_id = Column(String)                             # ID опитування
    chat_id = Column(Integer)                            # ID чату
    user_id = Column(Integer, ForeignKey("users.id"))    # Хто проголосував
    option_text = Column(String, nullable=True)          # 🆕 Вибраний варіант (текст)
    timestamp = Column(DateTime, default=datetime.utcnow) # Коли проголосував


# ❤️ Таблиця реакцій на повідомлення
class PostReaction(Base):
    __tablename__ = "post_reactions"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)                            # ID чату
    message_id = Column(Integer)                         # ID повідомлення
    user_id = Column(Integer, ForeignKey("users.id"))    # Хто поставив реакцію
    reaction = Column(String)                            # Тип реакції (наприклад "+", ❤️, 🔥)
    timestamp = Column(DateTime, default=datetime.utcnow) # Коли відреагував
    chat_title = Column(String, nullable=True)
    message_text = Column(String, nullable=True)


# 👥 Таблиця зв’язку користувачів із чатами
class ChatMember(Base):
    __tablename__ = "chat_members"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, index=True)                # ID чату
    user_id = Column(Integer, ForeignKey("users.id"))    # ID користувача
    joined_at = Column(DateTime, default=datetime.utcnow) # Коли додано в чат
