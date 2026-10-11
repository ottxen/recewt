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

class MonitorState(StatesGroup):
    waiting_for_username = State()

# --- DATABASE ---
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

# --- GENERATOR ---
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

def get_username(mode: str, length: int, with_digits: bool) -> str:
    if mode == "symmetric":
        return generate_symmetric(length)
    else:
        return generate_random(length, with_digits)

# --- KEYBOARDS ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⌕  Generate username", callback_data="menu_generate", style="success")],
        [InlineKeyboardButton(text="⏱  Check history", callback_data="menu_history")],
        [InlineKeyboardButton(text="☆  Saved names", callback_data="menu_saved")],
        [InlineKeyboardButton(text="👁  Monitor username", callback_data="menu_monitor")]
    ])

def generation_modes_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" • Symmetric search", callback_data="gen_mode_symmetric", style="success")],
        [InlineKeyboardButton(text=" • With digits", callback_data="gen_mode_digits")],
        [InlineKeyboardButton(text=" • Without digits", callback_data="gen_mode_nodigits")],
        [InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")]
    ])

def length_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 characters", callback_data="gen_len_5")],
        [InlineKeyboardButton(text="6 characters", callback_data="gen_len_6")],
        [InlineKeyboardButton(text="7 characters", callback_data="gen_len_7")],
        [InlineKeyboardButton(text="8 characters", callback_data="gen_len_8")],
        [InlineKeyboardButton(text="⎋  Back to modes", callback_data="menu_generate", style="danger")]
    ])

def result_kb(username: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⟳  Generate another", callback_data="gen_repeat", style="success")],
        [InlineKeyboardButton(text="💾  Save to favorites", callback_data=f"save_{username}")],
        [InlineKeyboardButton(text="↗  Check in Telegram", url=f"https://t.me/{username}")],
        [InlineKeyboardButton(text="⎋  Back to lengths", callback_data="gen_back_to_lengths", style="danger")]
    ])

# --- HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Welcome to R3gistry.\n\n"
        "A clean space for discovering unique and aesthetic usernames.\n"
        "Choose an option below:",
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

@router.callback_query(F.data == "menu_generate")
async def cb_generate_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Choose generation style:\n\n"
        "• Symmetric — harmonious mirrored combinations.\n"
        "• With / Without digits — random variations.",
        reply_markup=generation_modes_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("gen_mode_"))
async def cb_handle_mode(callback: CallbackQuery, state: FSMContext):
    mode_type = callback.data.split("_")[2]
    await state.update_data(mode=mode_type)
    
    await callback.message.edit_text(
        "Choose desired length (from 5 to 8 characters):",
        reply_markup=length_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "gen_back_to_lengths")
async def cb_back_to_lengths(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Choose desired length (from 5 to 8 characters):",
        reply_markup=length_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("gen_len_"))
async def cb_handle_generation(callback: CallbackQuery, state: FSMContext):
    length = int(callback.data.split("_")[2])
    data = await state.get_data()
    mode_type = data.get("mode", "digits")
    
    await state.update_data(length=length)
    
    with_digits = (mode_type == "digits" or mode_type == "symmetric")
    username = get_username(mode_type, length, with_digits)
    
    status_text = "Generated"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO history (user_id, username, status, created_at) VALUES (?, ?, ?, ?)",
            (callback.from_user.id, username, status_text, now_str)
        )
        await db.commit()

    await callback.message.edit_text(
        f"Generated option:\n\n"
        f"• @`{username}`\n\n"
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
    
    with_digits = (mode_type == "digits" or mode_type == "symmetric")
    username = get_username(mode_type, length, with_digits)
    
    status_text = "Generated"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO history (user_id, username, status, created_at) VALUES (?, ?, ?, ?)",
            (callback.from_user.id, username, status_text, now_str)
        )
        await db.commit()

    await callback.message.edit_text(
        f"Generated option:\n\n"
        f"• @`{username}`\n\n"
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
        text = "Your check history is currently empty."
    else:
        text = "Recently generated names:\n\n"
        for uname, date in rows:
            text += f"• @{uname} — {date}\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")]
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
        [InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "menu_monitor")
async def cb_monitor_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MonitorState.waiting_for_username)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⎋  Cancel", callback_data="menu_main", style="danger")]
    ])
    await callback.message.edit_text(
        "Username monito
        "Send the username you want to track. If it becomes available, the bot will notify you:",
        reply_markup=kb
    )
    await callback.answer()

@router.message(MonitorState.waiting_for_username)
async def process_monitor_input(message: Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    if not re.match(r"^[a-zA-Z0-9_]{5,}$", username):
        await message.answer("Invalid format. Use latin letters, numbers, and underscores (min 5 characters):")
        return
        
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO monitoring (user_id, username) VALUES (?, ?)",
            (message.from_user.id, username)
        )
        await db.commit()
        
    await state.clear()
    await message.answer(
        f"Name @{username} successfully added to monitoring.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")]
        ])
    )

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
        
