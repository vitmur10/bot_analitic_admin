from aiogram import types
from functools import wraps
from dotenv import load_dotenv
import os
load_dotenv()
TOKEN = os.getenv("TOKEN_BOT")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
NAME = os.getenv("NAME")
ALLOWED_USERNAMES = ["murvit10" , "Oleg_GrandCar"]
global_plus_tracking = {"active": False, "end_time": None, "user_ids": set()}

def admin_only(handler):
    async def wrapper(event, *args, **kwargs):
        from config import ALLOWED_USERNAMES
        username = getattr(event.from_user, "username", None)
        if not username or username.lower() not in [u.lower() for u in ALLOWED_USERNAMES]:
            try:
                await event.answer("⛔ Доступ заборонено.")
            except Exception:
                pass
            return

        # 🧠 фільтруємо службові аргументи Aiogram
        safe_kwargs = {
            k: v for k, v in kwargs.items()
            if k in handler.__code__.co_varnames
        }

        return await handler(event, *args, **safe_kwargs)
    return wrapper
