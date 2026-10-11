import asyncio
import logging
import re
import os
import random
from datetime import datetime

aiosqlite_available = True
try:
    import aiosqlite
except ImportError:
    aiosqlite_available = False

import aiohttp
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

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logging.error("❌ ERROR: BOT_TOKEN environment variable is not set!")
    exit(1)

router = Router()
DB_NAME = "bot_database.db"

# --- DATABASE ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users_config (
                user_id INTEGER PRIMARY KEY,
                length INTEGER DEFAULT 5,
                with_digits TEXT DEFAULT 'off'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
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

async def get_user_settings(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT length, with_digits FROM users_config WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"length": row[0], "with_digits": row[1]}
            else:
                await db.execute("INSERT INTO users_config (user_id, length, with_digits) VALUES (?, 5, 'off')", (user_id,))
                await db.commit()
                return {"length": 5, "with_digits": 'off'}

async def update_user_setting(user_id: int, key: str, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE users_config SET {key} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

# --- REAL AVAILABILITY CHECKER ---
async def check_username_availability(username: str) -> bool:
    clean_username = username.lstrip("@").lower()
    url = f"https://t.me/{clean_username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=4, allow_redirects=True) as response:
                html = await response.text()
                # Якщо сторінка вказує, що юзернейм вільний (немає інформації про профіль/канал)
                if "If you have Telegram, you can contact" not in html and "tgme_page_extra" not in html:
                    return True
                return False
    except Exception:
        return False

async def find_free_username(length: int, with_digits: str) -> str:
    chars_no_dig = "abcdefghijklmnopqrstuvwxyz"
    chars_dig = "abcdefghijklmnopqrstuvwxyz0123456789"
    charset = chars_dig if with_digits == 'on' else chars_no_dig
    
    # Робимо кілька спроб знайти вільний серед згенерованих
    for _ in range(30):
        uname = ''.join(random.choice(charset) for _ in range(length))
        is_free = await check_username_availability(uname)
        if is_free:
            return uname
            
    # Якщо за 30 спроб не знайшлося ідеально вільного, повертаємо хоча б останній згенерований
    return ''.join(random.choice(charset) for _ in range(length))

# --- KEYBOARDS ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⌕  Generate username", callback_data="menu_generate", style="success")],
        [InlineKeyboardButton(text="⚙  Filters & Settings", callback_data="menu_settings")],
        [InlineKeyboardButton(text="👤 Profile & Storage", callback_data="menu_profile")],
        [InlineKeyboardButton(text="👁  Monitor username", callback_data="menu_monitor")]
    ])

def settings_kb(config: dict):
    digits_text = "ON [✓]" if config["with_digits"] == 'on' else "OFF [✕]"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"Length: 5", callback_data="set_len_5", style="success" if config["length"]==5 else "primary"),
            InlineKeyboardButton(text=f"Length: 6", callback_data="set_len_6", style="success" if config["length"]==6 else "primary")
        ],
        [InlineKeyboardButton(text=f"Include digits: {digits_text}", callback_data="set_toggle_digits")],
        [InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")]
    ])

def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☆  Saved names", callback_data="menu_saved")],
        [InlineKeyboardButton(text="⏱  Generation history", callback_data="menu_history")],
        [InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")]
    ])

def result_kb(username: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾  Save to favorites", callback_data=f"save_{username}", style="primary")],
        [InlineKeyboardButton(text="↗  Check in Telegram", url=f"https://t.me/{username}")],
        [InlineKeyboardButton(text="⟳  Generate next", callback_data="menu_generate", style="success")],
        [InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")]
    ])

# --- HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await init_db()
    await message.answer(
        "Welcome to R3gistry.\n\n"
        "A clean space for discovering available 5–6 character Telegram usernames.\n"
        "Configure your filters or start generating below:",
        reply_markup=main_menu_kb()
    )

@router.callback_query(F.data == "menu_main")
async def cb_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Main menu.\n\nChoose an option below:", 
        reply_markup=main_menu_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "menu_settings")
async def cb_settings(callback: CallbackQuery):
    config = await get_user_settings(callback.from_user.id)
    text = (
        "Filters & Settings\n\n"
        f"• Target length: {config['length']} characters\n"
        f"• Include digits: {config['with_digits'].upper()}\n\n"
        "Customize your search parameters below:"
    )
    await callback.message.edit_text(text, reply_markup=settings_kb(config))
    await callback.answer()

@router.callback_query(F.data.startswith("set_len_"))
async def cb_set_length(callback: CallbackQuery):
    length = int(callback.data.split("_")[2])
    await update_user_setting(callback.from_user.id, "length", length)
    config = await get_user_settings(callback.from_user.id)
    
    text = (
        "Filters & Settings\n\n"
        f"• Target length: {config['length']} characters\n"
        f"• Include digits: {config['with_digits'].upper()}\n\n"
        "Customize your search parameters below:"
    )
    await callback.message.edit_text(text, reply_markup=settings_kb(config))
    await callback.answer()

@router.callback_query(F.data == "set_toggle_digits")
async def cb_toggle_digits(callback: CallbackQuery):
    config = await get_user_settings(callback.from_user.id)
    new_val = 'off' if config['with_digits'] == 'on' else 'on'
    await update_user_setting(callback.from_user.id, "with_digits", new_val)
    config = await get_user_settings(callback.from_user.id)
    
    text = (
        "Filters & Settings\n\n"
        f"• Target length: {config['length']} characters\n"
        f"• Include digits: {config['with_digits'].upper()}\n\n"
        "Customize your search parameters below:"
    )
    await callback.message.edit_text(text, reply_markup=settings_kb(config))
    await callback.answer()

@router.callback_query(F.data == "menu_profile")
async def cb_profile(callback: CallbackQuery):
    text = (
        "Profile & Storage\n\n"
        f"User ID: `{callback.from_user.id}`\n"
        "Manage your saved combinations and review history:"
    )
    await callback.message.edit_text(text, reply_markup=profile_kb(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "menu_generate")
async def cb_generate(callback: CallbackQuery):
    await callback.message.edit_text("⏱  Searching for an available username...")
    
    config = await get_user_settings(callback.from_user.id)
    username = await find_free_username(config["length"], config["with_digits"])
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO history (user_id, username, created_at) VALUES (?, ?, ?)",
            (callback.from_user.id, username, now_str)
        )
        await db.commit()

    text = (
        f"Available option found ({config['length']} chars, digits: {config['with_digits'].upper()}):\n\n"
        f"• @`{username}`\n\n"
        "Tap the button below to check it in Telegram or generate another one:"
    )

    await callback.message.edit_text(text, reply_markup=result_kb(username), parse_mode="Markdown")
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
        
    await callback.answer(f"Saved: @{username}", show_alert=True)

@router.callback_query(F.data == "menu_history")
async def cb_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT username, created_at FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        text = "Your generation history is currently empty."
    else:
        text = "Generation history (last 10):\n\n"
        for uname, date in rows:
            text += f"• @{uname} — {date}\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⎋  Back to profile", callback_data="menu_profile", style="danger")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
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
        text = "You haven't saved any names yet."
    else:
        text = "Your saved names:\n\n"
        for uname, saved_at in rows:
            text += f"• @{uname} [{saved_at}]\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⎋  Back to profile", callback_data="menu_profile", style="danger")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "menu_monitor")
async def cb_monitor_menu(callback: CallbackQuery, state: FSMContext):
    class MonitorState(StatesGroup):
        waiting_for_username = State()
        
    await state.set_state(MonitorState.waiting_for_username)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")]
    ])
    await callback.message.edit_text(
        "Username monitor\n\n"
        "Send the username you want to track:",
        reply_markup=kb
    )
    await callback.answer()

async def main():
    if not aiosqlite_available:
        print("Warning: aiosqlite missing.")
        return
        
    await init_db()
    
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    
    dp.include_router(router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    print("Bot successfully started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
            
