import asyncio
import datetime
import logging
import os
import random
import string
import sqlite3
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")

# 👇 Твій ID (власник) та ID хелпера
OWNER_ID = 5619415334       
HELPER_ID = 8644168067      

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- FSM STATES ---
class SearchStates(StatesGroup):
    waiting_for_length = State()
    waiting_for_digits = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_ban_id = State()
    waiting_for_unban_id = State()
    waiting_for_prem_id = State()
    waiting_for_prem_days = State()
    waiting_for_rem_prem_id = State()
    waiting_for_stats_days = State()
    waiting_for_code_input = State()

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            referrals_count INTEGER DEFAULT 0,
            total_invited INTEGER DEFAULT 0,
            premium_until TEXT,
            is_banned INTEGER DEFAULT 0,
            joined_date TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            created_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            saved_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS used_codes (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, referrer_id, referrals_count, total_invited, premium_until, is_banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def add_user(user_id: int, referrer_id: int = None):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        joined = datetime.datetime.now().isoformat()
        cursor.execute("INSERT INTO users (user_id, referrer_id, joined_date) VALUES (?, ?, ?)", (user_id, referrer_id, joined))
        conn.commit()
    conn.close()

def is_user_banned(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return False
    user = get_user(user_id)
    return bool(user[5]) if user else False

def is_user_premium(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    user = get_user(user_id)
    if not user or not user[4]:
        return False
    try:
        prem_date = datetime.datetime.fromisoformat(user[4])
        return prem_date > datetime.datetime.now()
    except Exception:
        return False

def add_to_history(user_id: int, username: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (user_id, username, created_at) VALUES (?, ?, ?)", 
                   (user_id, username, datetime.datetime.now().strftime("%d.%m %H:%M")))
    cursor.execute("""
        DELETE FROM history WHERE id NOT IN (
            SELECT id FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 20
        ) AND user_id = ?
    """, (user_id, user_id))
    conn.commit()
    conn.close()

def get_history(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, created_at FROM history WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def save_tag_to_db(user_id: int, username: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM saved_tags WHERE user_id = ? AND username = ?", (user_id, username))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO saved_tags (user_id, username, saved_at) VALUES (?, ?, ?)",
                       (user_id, username, datetime.datetime.now().strftime("%d.%m %H:%M")))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def get_saved_tags(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, saved_at FROM saved_tags WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_users_count_by_days(days: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    target_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined_date >= ?", (target_date,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_users_count_today():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined_date LIKE ?", (f"{today_str}%",))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# --- KEYBOARDS ---
def get_main_keyboard(user_id: int):
    keyboard = [
        [InlineKeyboardButton(text="🔍 Scan Usernames", callback_data="start_search")],
        [InlineKeyboardButton(text="💾 Saved Tags", callback_data="menu_saved"),
         InlineKeyboardButton(text="📜 History", callback_data="menu_history")],
        [InlineKeyboardButton(text="💎 Premium Status", callback_data="menu_premium")]
    ]
    
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton(text="👑 Owner Panel", callback_data="owner_menu")])
    elif user_id == HELPER_ID:
        keyboard.append([InlineKeyboardButton(text="🛠 Helper Panel", callback_data="helper_menu")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])

# --- MAIN MENU ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        aws_msg = "⛔ Your account has been blocked."
        await message.answer(aws_msg)
        return
        
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            potential_ref = int(args[1].replace("ref_", ""))
            if potential_ref != user_id:
                referrer_id = potential_ref
        except ValueError:
            pass

    user_data = get_user(user_id)
    if not user_data:
        add_user(user_id, referrer_id)

    status_tag = "STANDARD"
    if user_id == OWNER_ID:
        status_tag = "OWNER"
    elif user_id == HELPER_ID:
        status_tag = "HELPER"
    elif is_user_premium(user_id):
        status_tag = "PREMIUM"

    text = (
        f"<b>[ 🐈 USER SCOUT // SYSTEM ]</b>\n"
        f"Status: <code>{status_tag}</code>\n\n"
        "<i>Smart Telegram username scout & checker.</i>\n"
        "Choose an option below:"
    )
    await message.answer(text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")

@dp.callback_query(F.data == "menu_back")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    status_tag = "STANDARD"
    if user_id == OWNER_ID:
        status_tag = "OWNER"
    elif user_id == HELPER_ID:
        status_tag = "HELPER"
    elif is_user_premium(user_id):
        status_tag = "PREMIUM"

    text = (
        f"<b>[ 🐈 USER SCOUT // SYSTEM ]</b>\n"
        f"Status: <code>{status_tag}</code>\n\n"
        "<i>Smart Telegram username scout & checker.</i>\n"
        "Choose an option below:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

# --- OWNER PANEL ---
@dp.callback_query(F.data == "owner_menu")
async def owner_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Access denied.", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Users Stats", callback_data="own_stats")],
        [InlineKeyboardButton(text="🔨 Ban User", callback_data="own_ban"),
         InlineKeyboardButton(text="🔓 Unban User", callback_data="own_unban")],
        [InlineKeyboardButton(text="⚡ Give Premium", callback_data="own_give_prem"),
         InlineKeyboardButton(text="❌ Revoke Premium", callback_data="own_rem_prem")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    text = "<b>[ OWNER CONTROL PANEL ]</b>\n\nSelect an administration action:"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "own_stats")
async def owner_stats(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return
    today_count = get_users_count_today()
    total_7d = get_users_count_by_days(7)
    total_30d = get_users_count_by_days(30)
    
    text = (
        "<b>[ USER STATISTICS ]</b>\n\n"
        f"• Today: <code>{today_count}</code>\n"
        f"• Last 7 days: <code>{total_7d}</code>\n"
        f"• Last 30 days: <code>{total_30d}</code>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Owner Panel", callback_data="owner_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "own_ban")
async def own_ban_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminStates.waiting_for_ban_id)
    await callback.message.edit_text("<b>[ BAN USER ]</b>\n\nEnter User ID to ban:", reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(AdminStates.waiting_for_ban_id, F.text)
async def own_ban_process(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ User <code>{uid}</code> has been banned.", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Invalid User ID.")
    await state.clear()

@dp.callback_query(F.data == "own_unban")
async def own_unban_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminStates.waiting_for_unban_id)
    await callback.message.edit_text("<b>[ UNBAN USER ]</b>\n\nEnter User ID to unban:", reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(AdminStates.waiting_for_unban_id, F.text)
async def own_unban_process(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ User <code>{uid}</code> has been unbanned.", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Invalid User ID.")
    await state.clear()

@dp.callback_query(F.data == "own_rem_prem")
async def own_rem_prem_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminStates.waiting_for_rem_prem_id)
    await callback.message.edit_text("<b>[ REVOKE PREMIUM ]</b>\n\nEnter User ID to remove premium:", reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(AdminStates.waiting_for_rem_prem_id, F.text)
async def own_rem_prem_process(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        expired_date = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()
        cursor.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (expired_date, uid))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Premium successfully revoked from user <code>{uid}</code>.", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Invalid User ID.")
    await state.clear()

# --- HELPER PANEL ---
@dp.callback_query(F.data == "helper_menu")
async def helper_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.from_user.id != HELPER_ID:
        await callback.answer("⛔ Access denied.", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Give Premium", callback_data="hlp_give_prem"),
         InlineKeyboardButton(text="👥 Check Stats", callback_data="hlp_stats")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    text = "<b>[ HELPER CONTROL PANEL ]</b>\n\nSelect an action:"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "hlp_stats")
async def helper_stats(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != HELPER_ID: return
    await state.set_state(AdminStates.waiting_for_stats_days)
    text = "<b>[ USERS STATS ]</b>\n\nEnter number of days (e.g., <code>1</code>, <code>7</code>, <code>30</code>):"
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(AdminStates.waiting_for_stats_days, F.text)
async def helper_stats_process(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days == 1:
            count = get_users_count_today()
            label = "Today"
        else:
            count = get_users_count_by_days(days)
            label = f"Last {days} days"
        await message.answer(f"<b>[ STATS RESULT ]</b>\n{label}: <code>{count}</code> users.", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Invalid number.")
    await state.clear()

@dp.callback_query(F.data.in_({"own_give_prem", "hlp_give_prem"}))
async def give_prem_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in (OWNER_ID, HELPER_ID): return
    await state.set_state(AdminStates.waiting_for_prem_id)
    await callback.message.edit_text("<b>[ GIVE PREMIUM ]</b>\n\nEnter User ID:", reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(AdminStates.waiting_for_prem_id, F.text)
async def give_prem_id_process(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await state.update_data(target_uid=uid)
        await state.set_state(AdminStates.waiting_for_prem_days)
        await message.answer("Enter number of days for Premium:", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Invalid User ID.")
        await state.clear()

@dp.message(AdminStates.waiting_for_prem_days, F.text)
async def give_prem_days_process(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        data = await state.get_data()
        uid = data.get("target_uid")
        
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT premium_until FROM users WHERE user_id = ?", (uid,))
        row = cursor.fetchone()
        
        now = datetime.datetime.now()
        current_prem = datetime.datetime.fromisoformat(row[4]) if row and row[4] and datetime.datetime.fromisoformat(row[4]) > now else now
        new_prem = current_prem + datetime.timedelta(days=days)
        
        if not row:
            cursor.execute("INSERT OR IGNORE INTO users (user_id, premium_until, joined_date) VALUES (?, ?, ?)", 
                           (uid, new_prem.isoformat(), now.isoformat()))
        else:
            cursor.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_prem.isoformat(), uid))
            
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ Premium successfully granted to <code>{uid}</code> for {days} days.", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ Invalid days format.")
    await state.clear()

# --- SEARCH ENGINE (ВИПРАВЛЕНИЙ ПОШУК ТІЛЬКИ ВІЛЬНИХ ТЕГІВ) ---
@dp.callback_query(F.data == "start_search")
async def search_step_length(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.waiting_for_length)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5", callback_data="len_5"),
         InlineKeyboardButton(text="6", callback_data="len_6")],
        [InlineKeyboardButton(text="7", callback_data="len_7"),
         InlineKeyboardButton(text="8", callback_data="len_8"),
         InlineKeyboardButton(text="9", callback_data="len_9")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    text = "<b>[ SCOUT // STEP 1 ]</b>\n\nSelect exact username length (5 to 9):"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("len_"))
async def search_step_digits(callback: CallbackQuery, state: FSMContext):
    length = int(callback.data.replace("len_", ""))
    await state.update_data(exact_len=length)
    
    await state.set_state(SearchStates.waiting_for_digits)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="With digits (e.g. tag99)", callback_data="dig_yes")],
        [InlineKeyboardButton(text="Letters only (e.g. tag)", callback_data="dig_no")],
        [InlineKeyboardButton(text="← Back", callback_data="start_search")]
    ])
    text = f"<b>[ SCOUT // STEP 2 ]</b>\n\nLength: <b>{length} characters</b>.\nInclude digits?"
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("dig_"))
async def process_username_search(callback: CallbackQuery, state: FSMContext):
    use_digits = (callback.data == "dig_yes")
    data = await state.get_data()
    length = data.get("exact_len", 5)
    
    user_id = callback.from_user.id
    is_prem = is_user_premium(user_id)
    limit = 3 if is_prem else 1

    await callback.message.edit_text("<b>[ 🐈 SCOUTING ]</b>\nScanning Telegram network for truly available tags...", parse_mode="HTML")
    
    found_usernames = []
    chars = string.ascii_lowercase + (string.digits if use_digits else "")
    
        attempts = 0
    while len(found_usernames) < limit and attempts < 80:
        attempts += 1
        uname = "".join(random.choices(chars, k=length))
        
        if uname[0].isdigit():
            continue
            
        try:
            await bot.get_chat(f"@{uname}")
        except TelegramBadRequest as e:
            err_msg = str(e).lower()
            if "chat not found" in err_msg or "username not found" in err_msg:
                if uname not in found_usernames:
                    found_usernames.append(uname)
        except Exception:
            pass
        await asyncio.sleep(0.02)

    if not found_usernames:
        text = "<b>[ ⚠️ RESULT ]</b>\n\nNo available tags found. Try different settings."
        await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
        return

    result_lines = []
    keyboard_buttons = []
    
    for uname in found_usernames:
        add_to_history(user_id, uname)
        result_lines.append(f"• <code>@{uname}</code> — <b>Available ✅</b>")
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"🔗 Open @{uname}", url=f"https://t.me/{uname}"),
            InlineKeyboardButton(text=f"💾 Save", callback_data=f"save_{uname}")
        ])

    usernames_joined = "\n".join(result_lines)
    mode_text = 'PREMIUM (3 slots)' if is_prem else 'STANDARD (1 slot)'
    
    result_text = (
        f"<b>[ 🐈 SCOUT RESULTS ]</b>\n\n"
        f"{usernames_joined}\n\n"
        f"Mode: <code>{mode_text}</code>"
    )

    promo_drop_text = ""
    valid_codes = ["PREMIUM2026", "NEWBOTUSERNAME", "START", "SEARCHUSERNAME"]
    if random.random() < 0.15:
        dropped_code = random.choice(valid_codes)
        promo_drop_text = f"\n\n🎁 <b>Lucky Drop!</b> You found a hidden promo code: <code>{dropped_code}</code>\nActivate it in the Premium menu."

    result_text += promo_drop_text

    keyboard_buttons.append([InlineKeyboardButton(text="🔄 Scout Again", callback_data="start_search")])
    keyboard_buttons.append([InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")])
    
    result_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await callback.message.edit_text(result_text, reply_markup=result_keyboard, parse_mode="HTML")
    await state.clear()
    await callback.answer()

# --- SAVED TAGS & HISTORY ---
@dp.callback_query(F.data == "menu_saved")
async def show_saved_tags(callback: CallbackQuery):
    user_id = callback.from_user.id
    rows = get_saved_tags(user_id)
    
    if not rows:
        text = "<b>[ SAVED TAGS ]</b>\n\nYou have no saved tags."
    else:
        list_str = "\n".join([f"• <code>@{item[0]}</code> — <i>{item[1]}</i>" for item in rows])
        text = f"<b>[ SAVED TAGS ]</b>\n\n{list_str}"
        
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("save_"))
async def save_tag_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    uname = callback.data.replace("save_", "")
    is_saved = save_tag_to_db(user_id, uname)
    if is_saved:
        await callback.answer(f"✅ @{uname} successfully saved.", show_alert=True)
    else:
        await callback.answer(f"⚠️ @{uname} is already saved.", show_alert=True)

@dp.callback_query(F.data == "menu_history")
async def show_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    history_rows = get_history(user_id)
    
    if not history_rows:
        text = "<b>[ HISTORY ]</b>\n\nHistory is empty."
    else:
        history_list = "\n".join([f"• <code>@{item[0]}</code> — <i>{item[1]}</i>" for item in history_rows])
        text = f"<b>[ HISTORY (Last 20) ]</b>\n\n{history_list}"
        
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- PREMIUM & PROMO CODES SYSTEM ---
@dp.callback_query(F.data == "menu_premium")
async def show_premium_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_data = get_user(user_id)
    prem_until_str = user_data[4] if user_data else None
    
    prem_status = "Inactive ❌"
    if user_id == OWNER_ID:
        prem_status = "Active (Owner 👑) ✅"
    elif user_id == HELPER_ID:
        prem_status = "Active (Helper 🛠) ✅"
    elif prem_until_str:
        prem_date = datetime.datetime.fromisoformat(prem_until_str)
        if prem_date > datetime.datetime.now():
            prem_status = f"Active until {prem_date.strftime('%d.%m %H:%M')} ✅"

    text = (
        "<b>[ PREMIUM SYSTEM ]</b>\n\n"
        f"Status: <b>{prem_status}</b>\n\n"
        "<b>Perks:</b> Scan up to 3 available usernames simultaneously.\n\n"
        "💡 Have a promo code? Enter it to get +1 day of Premium!"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Activate Promo Code", callback_data="enter_promo")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "enter_promo")
async def enter_promo_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_code_input)
    text = "<b>[ PROMO CODE ]</b>\n\nSend your promo code in chat:"
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(AdminStates.waiting_for_code_input, F.text)
async def process_promo_code(message: Message, state: FSMContext):
    code_input = message.text.strip().upper()
    user_id = message.from_user.id
    
    valid_codes = ["PREMIUM2026", "NEWBOTUSERNAME", "START", "SEARCHUSERNAME"]
    
    if code_input not in valid_codes:
        await message.answer("❌ Invalid promo code.")
        await state.clear()
        return

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM used_codes WHERE user_id = ? AND code = ?", (user_id, code_input))
    if cursor.fetchone():
        conn.close()
        await message.answer("⚠️ You have already used this promo code.")
        await state.clear()
        return

    cursor.execute("INSERT INTO used_codes (user_id, code) VALUES (?, ?)", (user_id, code_input))
    
    cursor.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    now = datetime.datetime.now()
    current_prem = datetime.datetime.fromisoformat(row[4]) if row and row[4] and datetime.datetime.fromisoformat(row[4]) > now else now
    new_prem = current_prem + datetime.timedelta(days=1)
    
    cursor.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (new_prem.isoformat(), user_id))
    conn.commit()
    conn.close()

    await message.answer(f"✅ Success! Promo code <code>{code_input}</code> activated. +1 day added.", parse_mode="HTML")
    await state.clear()

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("User Scout (Cat Edition) is online!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
        
