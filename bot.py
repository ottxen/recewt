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

# --- ADVANCED UNIC/CLEAN GENERATOR ---
PREFIXES = ["get", "my", "use", "try", "the", "core", "app", "io"]
ROOTS = ["flux", "vibe", "aura", "shift", "loop", "sync", "pulse", "apex", "zen", "mesh", "flow", "nova"]
SUFFIXES = ["hq", "io", "ai", "app", "lab", "hub"]

def generate_smart_usernames(count: int = 5) -> list:
    results = set()
    while len(results) < count:
        style = random.choice([1, 2, 3])
        if style == 1:
            # Наприклад: fluxloop, aurasync
            uname = random.choice(ROOTS) + random.choice(ROOTS)
        elif style == 2:
            # Наприклад: getvibe, tryflux
            uname = random.choice(PREFIXES) + random.choice(ROOTS)
        else:
            # Наприклад: flowio, zenlab
            uname = random.choice(ROOTS) + random.choice(SUFFIXES)
        
        # Додаємо трохи випадковості для унікальності
        if random.random() > 0.5 and len(uname) < 10:
            uname += str(random.randint(1, 99))
            
        results.add(uname)
    return list(results)

# --- KEYBOARDS ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⌕  Generate usernames", callback_data="menu_generate", style="success")],
        [InlineKeyboardButton(text="⏱  Check history", callback_data="menu_history")],
        [InlineKeyboardButton(text="☆  Saved names", callback_data="menu_saved")],
        [InlineKeyboardButton(text="👁  Monitor username", callback_data="menu_monitor")]
    ])

def result_kb(usernames_list: list):
    keyboard = []
    # Додаємо кнопки для кожного згенерованого варіанту (щоб зберегти чи перевірити)
    for uname in usernames_list:
        keyboard.append([InlineKeyboardButton(text=f"💾 Save @{uname}", callback_data=f"save_{uname}")])
    
    keyboard.append([InlineKeyboardButton(text="⟳  Generate batch", callback_data="gen_repeat", style="success")])
    keyboard.append([InlineKeyboardButton(text="⎋  Main menu", callback_data="menu_main", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- HANDLERS ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Welcome to R3gistry.\n\n"
        "A clean space for discovering modern brand combinations and unique usernames.\n"
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
    
    usernames = generate_smart_usernames(5)
    await state.update_data(last_batch=usernames)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        for uname in usernames:
            await db.execute(
                "INSERT INTO history (user_id, username, status, created_at) VALUES (?, ?, ?, ?)",
                (callback.from_user.id, uname, "Generated", now_str)
            )
        await db.commit()

    text = "Fresh generated username ideas:\n\n"
    for uname in usernames:
        text += f"• @`{uname}` — (Check in Telegram: t.me/{uname})\n"
    text += "\nChoose an action below:"

    await callback.message.edit_text(text, reply_markup=result_kb(usernames), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "gen_repeat")
async def cb_gen_repeat(callback: CallbackQuery, state: FSMContext):
    usernames = generate_smart_usernames(5)
    await state.update_data(last_batch=usernames)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        for uname in usernames:
            await db.execute(
                "INSERT INTO history (user_id, username, status, created_at) VALUES (?, ?, ?, ?)",
                (callback.from_user.id, uname, "Generated", now_str)
            )
        await db.commit()

    text = "Fresh generated username ideas:\n\n"
    for uname in usernames:
        text += f"• @`{uname}` — (Check in Telegram: t.me/{uname})\n"
    text += "\nChoose an action below:"

    await callback.message.edit_text(text, reply_markup=result_kb(usernames), parse_mode="Markdown")
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
        "Username monitor\n\n"
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
    
