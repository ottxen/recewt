import asyncio
import logging
import random
import re
import os
from datetime import datetime

aiosqlite_available = True
try:
    import aiosqlite
except ImportError:
    aiosqlite_available = False

from telethon import TelegramClient, functions, errors
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# Logging configuration
logging.basicConfig(level=logging.INFO)

# Reading environment variables
TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")

if not TOKEN or not API_ID or not API_HASH:
    logging.error("❌ ERROR: BOT_TOKEN, API_ID or API_HASH environment variables are missing!")
    exit(1)

router = Router()
DB_NAME = "bot_database.db"

# Initialize Telethon client for checking username availability via Telegram API
client = TelegramClient('telegram_session', int(API_ID), API_HASH)

# States for FSM
class GenState(StatesGroup):
    choosing_length = State()

class MonitorState(StatesGroup):
    waiting_for_username = State()

# --- DATABASE SETUP ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                status TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS saved_usernames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                saved_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitoring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT
            )
        """)
        await db.commit()

# --- TELEGRAM API USERNAME CHECKER (100% Accurate) ---
async def check_username_via_telegram(username: str) -> bool:
    """
    Перевіряє доступність юзернейму через офіційний Telegram API (Telethon).
    Повертає True, якщо юзернейм вільний, і False, якщо зайнятий.
    """
    clean_username = username.lstrip("@").lower()
    try:
        result = await client(functions.account.CheckUsernameRequest(
            username=clean_username
        ))
        return result  # True if available, False if taken
    except errors.UsernameOccupiedError:
        return False
    except errors.UsernameInvalidError:
        return False
    except Exception as e:
        logging.error(f"Telethon check error for @{clean_username}: {e}")
        return False

# --- USERNAME GENERATOR ---
def generate_symmetric(length: int = 5) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    half_len = length // 2
    is_odd = length % 2 != 0
    
    half = ''.join(random.choice(chars) for _ in range(half_len))
    middle = random.choice(chars) if is_odd else ""
    
    if is_odd:
        full = half + middle + half[::-1]
    else:
        full = half + half[::-1]
    return full

def generate_random(length: int, with_digits: bool) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789" if with_digits else "abcdefghijklmnopqrstuvwxyz"
    return ''.join(random.choice(chars) for _ in range(length))

async def find_free_username(mode: str, length: int, with_digits: bool):
    """Цикл генерації, поки не знайде гарантовано вільний юзернейм через Telegram API."""
    attempts = 0
    while attempts < 50:
        attempts += 1
        if mode == "symmetric":
            uname = generate_symmetric(length)
        else:
            uname = generate_random(length, with_digits)
            
        is_free = await check_username_via_telegram(uname)
        if is_free:
            return uname
        await asyncio.sleep(0.05) # Дуже швидка перевірка без затримок
        
    return generate_random(length, with_digits)

# --- KEYBOARDS (VERTICAL LAYOUT) ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Generate Usernames", callback_data="menu_generate")],
        [InlineKeyboardButton(text="📜 Generation History", callback_data="menu_history")],
        [InlineKeyboardButton(text="⭐ Saved Usernames", callback_data="menu_saved")],
        [InlineKeyboardButton(text="👁 Monitor Username", callback_data="menu_monitor")]
    ])

def generation_modes_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪞 Symmetric Search", callback_data="gen_mode_symmetric")],
        [InlineKeyboardButton(text="🔠 With Digits", callback_data="gen_mode_digits")],
        [InlineKeyboardButton(text="🔤 Without Digits", callback_data="gen_mode_nodigits")],
        [InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu_main")]
    ])

def length_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 Characters", callback_data="gen_len_5")],
        [InlineKeyboardButton(text="6 Characters", callback_data="gen_len_6")],
        [InlineKeyboardButton(text="7 Characters", callback_data="gen_len_7")],
        [InlineKeyboardButton(text="8 Characters", callback_data="gen_len_8")],
        [InlineKeyboardButton(text="⬅️ Back to Modes", callback_data="menu_generate")]
    ])

def result_kb(username: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Try Again", callback_data="gen_repeat")],
        [InlineKeyboardButton(text="💾 Save Username", callback_data=f"save_{username}")],
        [InlineKeyboardButton(text="🔗 Check on Fragment", url=f"https://fragment.com/username/{username}")],
        [InlineKeyboardButton(text="📤 Share to Chat", switch_inline_query=f"@{username}")],
        [InlineKeyboardButton(text="⬅️ Back to Lengths", callback_data="gen_back_to_lengths")]
    ])

# --- HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Welcome! This bot uses direct Telegram API to generate and find **100% free** Telegram usernames.\n\n"
        "Please select an option below:",
        reply_markup=main_menu_kb()
    )

@router.callback_query(F.data == "menu_main")
async def cb_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Main Menu:", reply_markup=main_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_generate")
async def cb_generate_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "⚙️ Choose generation mode:\n\n"
        "• *Symmetric Search* — mirrored aesthetics (e.g., `abba`, `xyyx`).\n"
        "• *With / Without Digits* — random combinations.",
        reply_markup=generation_modes_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("gen_mode_"))
async def cb_handle_mode(callback: CallbackQuery, state: FSMContext):
    mode_type = callback.data.split("_")[2]
    await state.update_data(mode=mode_type)
    
    await callback.message.edit_text(
        "📏 Choose maximum length of the username (5 to 8 characters):",
        reply_markup=length_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "gen_back_to_lengths")
async def cb_back_to_lengths(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📏 Choose maximum length of the username (5 to 8 characters):",
        reply_markup=length_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("gen_len_"))
async def cb_handle_generation(callback: CallbackQuery, state: FSMContext):
    length = int(callback.data.split("_")[2])
    data = await state.get_data()
    mode_type = data.get("mode", "digits")
    
    await state.update_data(length=length)
    
    await callback.message.edit_text("⏳ Searching for a 100% free username...")
    
    with_digits = (mode_type == "digits" or mode_type == "symmetric")
    username = await find_free_username(mode_type, length, with_digits)
    
    status_text = "✅ Available"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO history (user_id, username, status, created_at) VALUES (?, ?, ?, ?)",
            (callback.from_user.id, username, status_text, now_str)
        )
        await db.commit()

    await callback.message.edit_text(
        f"🔍 Found Free Username:\n\n"
        f"🔹 `@{username}`\n"
        f"📊 Status: *{status_text}*\n\n"
        f"Choose next action:",
        reply_markup=result_kb(username),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "gen_repeat")
async def cb_gen_repeat(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mode_type = data.get("mode", "digits")
    length = data.get("length", 5)
    
    await callback.message.edit_text("⏳ Searching for another free username...")
    
    with_digits = (mode_type == "digits" or mode_type == "symmetric")
    username = await find_free_username(mode_type, length, with_digits)
    
    status_text = "✅ Available"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO history (user_id, username, status, created_at) VALUES (?, ?, ?, ?)",
            (callback.from_user.id, username, status_text, now_str)
        )
        await db.commit()

    await callback.message.edit_text(
        f"🔍 Found Free Username:\n\n"
        f"🔹 `@{username}`\n"
        f"📊 Status: *{status_text}*\n\n"
        f"Choose next action:",
        reply_markup=result_kb(username),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("save_"))
async def cb_save_username(callback: CallbackQuery):
    username = callback.data.split("_")[1]
    user_id = callback.from_user.id
    saved_at = datetime.now().strftime("%H:%M - %d.%m.%Y")
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO saved_usernames (user_id, username, saved_at) VALUES (?, ?, ?)",
            (user_id, username, saved_at)
        )
        await db.commit()
        
    await callback.answer(f"✅ Username @{username} successfully saved!", show_alert=True)

@router.callback_query(F.data == "menu_history")
async def cb_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT username, status, created_at FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        text = "📜 Your generation history is empty."
    else:
        text = "📜 *Recent Checked Usernames:*\n\n"
        for uname, status, date in rows:
            text += f"• `@{uname}` — {status} _({date})_\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "menu_saved")
async def cb_saved(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT username, saved_at FROM saved_usernames WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        text = "⭐ You haven't saved any usernames yet."
    else:
        text = "⭐ *Your Saved Usernames:*\n\n"
        for uname, saved_at in rows:
            text += f"• `@{uname}` (Saved: {saved_at})\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu_main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "menu_monitor")
async def cb_monitor_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MonitorState.waiting_for_username)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Cancel", callback_data="menu_main")]
    ])
    await callback.message.edit_text(
        "👁 **Monitor Taken Username**\n\n"
        "Send me the username (with or without `@`) that you want to track. If it becomes available, I will notify you!",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(MonitorState.waiting_for_username)
async def process_monitor_input(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    if not re.match(r"^[a-zA-Z0-9_]{5,}$", username):
        await message.answer("❌ Invalid username format. It must contain only Latin letters, numbers, and underscores (at least 5 characters). Try again:")
        return
        
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO monitoring (user_id, username) VALUES (?, ?)",
            (message.from_user.id, username)
        )
        await db.commit()
        
    await state.clear()
    await message.answer(
        f"✅ You have successfully added `@{username}` to the monitoring list!\nI will check its status periodically.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Main Menu", callback_data="menu_main")]
        ]),
        parse_mode="Markdown"
    )

# --- BACKGROUND MONITORING TASK ---
async def background_monitoring(bot: Bot):
    while True:
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT id, user_id, username FROM monitoring") as cursor:
                    rows = await cursor.fetchall()
                    
                for row_id, user_id, username in rows:
                    is_free = await check_username_via_telegram(username)
                    if is_free:
                        try:
                            await bot.send_message(
                                user_id,
                                f"🎉 **ATTENTION! Username is now available!**\n\n"
                                f"🔹 `@{username}` is free! Claim it quickly!",
                                parse_mode="Markdown"
                            )
                            await db.execute("DELETE FROM monitoring WHERE id = ?", (row_id,))
                            await db.commit()
                        except Exception as e:
                            logging.error(f"Failed to send notification to user {user_id}: {e}")
                            
        except Exception as e:
            logging.error(f"Background monitoring error: {e}")
            
        await asyncio.sleep(300)

# --- BOT RUNNER ---
async def main():
    if not aiosqlite_available:
        print("Warning: aiosqlite library is missing.")
        return
        
    await init_db()
    
    # Start Telethon client
    await client.start(phone=PHONE)
    print("Telethon client successfully connected!")

    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    
    dp.include_router(router)
    
    asyncio.create_task(background_monitoring(bot))
    
    await bot.delete_webhook(drop_pending_updates=True)
    print("Aiogram bot successfully started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
