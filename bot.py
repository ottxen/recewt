import asyncio
import datetime
import logging
import os
import random
import sqlite3
import string
import sys
from urllib.parse import urlparse
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
import cv2

TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("secur3ty.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_passwords (
            user_id INTEGER,
            password TEXT,
            saved_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_password_db(user_id: int, password: str):
    conn = sqlite3.connect("secur3ty.db")
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO saved_passwords (user_id, password, saved_at) VALUES (?, ?, ?)", (user_id, password, now))
    conn.commit()
    conn.close()

def get_saved_passwords_db(user_id: int):
    conn = sqlite3.connect("secur3ty.db")
    cursor = conn.cursor()
    cursor.execute("SELECT password, saved_at FROM saved_passwords WHERE user_id = ? ORDER BY rowid DESC LIMIT 15", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- DETAILED URL & THREAT ANALYSIS HELPER ---
def analyze_url_deep(url: str):
    url_lower = url.lower()
    
    # Check for stuffed or multiple concatenated links
    if url_lower.count("http://") > 1 or url_lower.count("https://") > 1 or "http" in url_lower[5:]:
        return (
            "<b>target domain:</b> <code>multiple / malformed urls detected</code>\n"
            "<b>security status:</b> <b>high risk ❌ (url obfuscation detected)</b>\n\n"
            "<i>warning: this link contains merged or hidden urls designed to disguise its real destination.</i>"
        )

    if not url.startswith(("http://", "https://")):
        full_url = "http://" + url
    else:
        full_url = url

    parsed = urlparse(full_url)
    domain = parsed.netloc or parsed.path.split('/')[0]
    path = parsed.path
    query = parsed.query

    # Threat and payload keyword matching
    danger_words = ["virus", "cure", "hack", "stealer", "grabber", "bot", "token", "payload", "malware", "exploit"]
    has_danger_words = any(word in url_lower for word in danger_words)
    is_trusted_domain = any(trusted in domain.lower() for trusted in ["icloud.com", "apple.com", "google.com", "t.me"])
    
    risk_status = "safe & clean ✅"
    if has_danger_words or "@" in url or len(query) > 80:
        risk_status = "high risk / potential exploit ❌"
        if is_trusted_domain:
            risk_status = "high risk ❌ (trusted domain abused for payload delivery)"

    clean_url = url.split("?")[0]

    report = (
        f"• <b>target domain:</b> <code>{domain}</code>\n"
        f"• <b>endpoint path:</b> <code>{path if path else '/'}</code>\n"
        f"• <b>protocol check:</b> <code>{'valid' if parsed.scheme in ['http', 'https'] else 'malformed ⚠️'}</code>\n"
        f"• <b>clean url:</b> <code>{clean_url}</code>\n\n"
        f"<b>security status:</b> <b>{risk_status}</b>"
    )
    
    if has_danger_words or "@" in url:
        report += "\n\n<i>warning: suspicious markers found in parameters or link structure.</i>"
        
    return report

# --- FSM STATES ---
class ToolStates(StatesGroup):
    waiting_for_url = State()

# --- MAIN KEYBOARD ---
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 check url safety", callback_data="tool_url"),
         InlineKeyboardButton(text="📷 scan qr code", callback_data="tool_qr")],
        [InlineKeyboardButton(text="🛡 file inspector", callback_data="tool_file"),
         InlineKeyboardButton(text="🔑 password manager", callback_data="tool_pass")],
        [InlineKeyboardButton(text="ℹ️ about secur3tybot", callback_data="tool_about")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← main menu", callback_data="menu_back")]
    ])

# --- START COMMAND ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "<b>secur3tybot // system</b>\n\n"
        "welcome to your digital security toolkit.\n"
        "select a tool below to begin:"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "menu_back")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "<b>secur3tybot // system</b>\n\n"
        "main menu. select a tool:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "tool_about")
async def about_bot(callback: CallbackQuery):
    text = (
        "<b>about secur3tybot</b>\n\n"
        "minimalist digital security utility:\n"
        "• deep url & payload analysis\n"
        "• qr code decoder with link verification\n"
        "• file extension & threat inspector\n"
        "• password generator & private vault\n\n"
        "<i>stay safe online.</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- 1. URL SAFETY CHECKER ---
@dp.callback_query(F.data == "tool_url")
async def url_tool_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ToolStates.waiting_for_url)
    text = (
        "<b>url safety checker</b>\n\n"
        "send or paste the url you want to inspect:"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(ToolStates.waiting_for_url, F.text)
async def process_url_check(message: Message, state: FSMContext):
    url = message.text.strip()
    analysis_result = analyze_url_deep(url)
    
    text = (
        f"<b>url analysis report</b>\n\n"
        f"input: <code>{url[:50]}...</code>\n\n"
        f"{analysis_result}"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 check another url", callback_data="tool_url")],
        [InlineKeyboardButton(text="← main menu", callback_data="menu_back")]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()

# --- 2. QR CODE SCANNER ---
@dp.callback_query(F.data == "tool_qr")
async def qr_tool_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "<b>qr code scanner</b>\n\n"
        "send an image containing a qr code as a photo to decode and analyze its target:"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(F.photo)
async def process_qr_photo(message: Message):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    
    temp_path = f"temp_{message.from_user.id}.jpg"
    with open(temp_path, "wb") as f:
        f.write(file_bytes.read() if hasattr(file_bytes, "read") else file_bytes)
        
    try:
        img = cv2.imread(temp_path)
        detector = cv2.QRCodeDetector()
        qr_data, _, _ = detector.detectAndDecode(img)
        
        if not qr_data:
            text = "<b>qr scan result</b>\n\nno qr code detected in this image. try uploading a clearer image."
        else:
            if "." in qr_data and " " not in qr_data:
                link_analysis = analyze_url_deep(qr_data)
                text = (
                    f"<b>qr code decoded & analyzed</b>\n\n"
                    f"raw content:\n<code>{qr_data}</code>\n\n"
                    f"<b>destination report:</b>\n{link_analysis}"
                )
            else:
                text = (
                    f"<b>qr code decoded</b>\n\n"
                    f"content:\n<code>{qr_data}</code>\n\n"
                    f"<i>type: plain text format (safe)</i>"
                )
    except Exception:
        text = "<b>error</b>\n\ncould not process the image. please try another file."
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← main menu", callback_data="menu_back")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# --- 3. FILE INSPECTOR ---
@dp.callback_query(F.data == "tool_file")
async def file_tool_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "<b>file inspector</b>\n\n"
        "send any file or document to inspect its format, extension, and risk profile:"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(F.document | F.audio | F.video)
async def process_file_inspection(message: Message):
    document = message.document or message.audio or message.video
    file_name = getattr(document, "file_name", "unknown_file")
    file_size = getattr(document, "file_size", 0)
    mime_type = getattr(document, "mime_type", "application/octet-stream")
    
    ext = file_name.split(".")[-1].lower() if "." in file_name else ""
    
    dangerous_extensions = ["exe", "scr", "bat", "cmd", "js", "vbs", "pif", "msi", "jar", "apk"]
    warning_extensions = ["zip", "rar", "7z", "iso", "docm", "xlsm"]
    
    risk_level = "safe standard format ✅"
    if ext in dangerous_extensions:
        risk_level = "high risk ❌ (executable / script format)"
    elif ext in warning_extensions:
        risk_level = "moderate warning ⚠️ (compressed container)"
        
    size_mb = round(file_size / (1024 * 1024), 2)
    
    text = (
        f"<b>file inspection report</b>\n\n"
        f"• file name: <code>{file_name}</code>\n"
        f"• size: <code>{size_mb} mb</code>\n"
        f"• mime type: <code>{mime_type}</code>\n"
        f"• extension: <code>.{ext}</code>\n\n"
        f"<b>security assessment:</b> <b>{risk_level}</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← main menu", callback_data="menu_back")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# --- 4. PASSWORD MANAGER & GENERATOR ---
@dp.callback_query(F.data == "tool_pass")
async def password_manager_menu(callback: CallbackQuery):
    text = (
        "<b>password manager</b>\n\n"
        "generate secure credentials or manage saved keys in your vault:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ generate new password", callback_data="gen_password")],
        [InlineKeyboardButton(text="📁 view saved passwords", callback_data="view_saved_passes")],
        [InlineKeyboardButton(text="← main menu", callback_data="menu_back")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "gen_password")
async def generate_password_action(callback: CallbackQuery):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = "".join(random.choices(chars, k=16))
    
    text = (
        "<b>generated password</b>\n\n"
        f"<code>{password}</code>\n\n"
        "<i>tap code to copy, or select an option:</i>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 save to vault", callback_data=f"save_pass_{password}"),
         InlineKeyboardButton(text="📤 send to chat", callback_data=f"send_pass_{password}")],
        [InlineKeyboardButton(text="🔄 generate another", callback_data="gen_password")],
        [InlineKeyboardButton(text="← password menu", callback_data="tool_pass")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("save_pass_"))
async def save_password_callback(callback: CallbackQuery):
    password = callback.data.replace("save_pass_", "")
    user_id = callback.from_user.id
    save_password_db(user_id, password)
    await callback.answer("✅ password saved to your vault!", show_alert=True)

@dp.callback_query(F.data.startswith("send_pass_"))
async def send_password_callback(callback: CallbackQuery):
    password = callback.data.replace("send_pass_", "")
    await callback.message.answer(f"🔑 password:\n<code>{password}</code>", parse_mode="HTML")
    await callback.answer("sent to chat!")

@dp.callback_query(F.data == "view_saved_passes")
async def view_saved_passwords(callback: CallbackQuery):
    user_id = callback.from_user.id
    rows = get_saved_passwords_db(user_id)
    
    if not rows:
        text = "<b>saved passwords vault</b>\n\nyour vault is currently empty."
    else:
        pass_list = "\n".join([f"• <code>{item[0]}</code> — <i>{item[1]}</i>" for item in rows])
        text = f"<b>saved passwords vault</b>\n\n{pass_list}"
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← password menu", callback_data="tool_pass")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("secur3tybot is online and running!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
            
