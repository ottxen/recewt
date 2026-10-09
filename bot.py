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
    if not url.startswith(("http://", "https://")):
        full_url = "http://" + url
    else:
        full_url = url

    parsed = urlparse(full_url)
    domain = parsed.netloc or parsed.path.split('/')[0]
    path = parsed.path
    
    # Check for common URL shorteners that hide real destination
    shorteners = ["bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly", "adf.ly", "clck.ru"]
    is_shortener = any(s in domain.lower() for s in shorteners)

    # Check for phishing/suspicious keywords in the link
    suspicious_keywords = ["login", "verify", "update", "secure", "account", "banking", "free", "gift", "bonus", "support", "auth", "admin"]
    parsed_lower = url.lower()
    has_suspicious_words = any(kw in parsed_lower for kw in suspicious_keywords)

    # Risk Assessment
    risk_status = "Safe & Clean ✅"
    if is_shortener:
        risk_status = "Moderate Risk ⚠️ (URL Shortener hides final destination)"
    if has_suspicious_words and (parsed.scheme == "http" or is_shortener or len(url) > 40):
        risk_status = "High Risk / Potential Phishing ❌"

    clean_url = url.split("?")[0]

    report = (
        f"• <b>Target Domain (Where it leads):</b> <code>{domain}</code>\n"
        f"• <b>Path / Endpoint:</b> <code>{path if path else '/'}</code>\n"
        f"• <b>Protocol:</b> <code>{'HTTPS (Encrypted)' if parsed.scheme == 'https' else 'HTTP (Insecure ⚠️)'}</code>\n"
        f"• <b>Masked / Shortened Link:</b> <code>{'Yes (Hidden destination ⚠️)'}</code>" if is_shortener else 
        f"• <b>Masked / Shortened Link:</b> <code>No (Direct link)</code>\n"
        f"• <b>Clean URL (No Trackers):</b> <code>{clean_url}</code>\n\n"
        f"<b>Security Verdict:</b> <b>{risk_status}</b>"
    )
    return report

# --- FSM STATES ---
class ToolStates(StatesGroup):
    waiting_for_url = State()

# --- MAIN KEYBOARD ---
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Check URL Safety", callback_data="tool_url"),
         InlineKeyboardButton(text="📷 Scan QR Code", callback_data="tool_qr")],
        [InlineKeyboardButton(text="🛡 File Inspector", callback_data="tool_file"),
         InlineKeyboardButton(text="🔑 Password Manager", callback_data="tool_pass")],
        [InlineKeyboardButton(text="ℹ️ About secur3tybot", callback_data="tool_about")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])

# --- START COMMAND ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "<b>[ 🛡 SECUR3TYBOT // SYSTEM ]</b>\n\n"
        "Welcome! Your personal digital safety toolkit.\n"
        "Choose a tool below to get started:"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="HTML")

@dp.callback_query(F.data == "menu_back")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "<b>[ 🛡 SECUR3TYBOT // SYSTEM ]</b>\n\n"
        "Main menu. Choose a tool:"
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "tool_about")
async def about_bot(callback: CallbackQuery):
    text = (
        "<b>[ ABOUT SECUR3TYBOT ]</b>\n\n"
        "<b>secur3tybot</b> is a minimalist utility bot designed to help you analyze potential digital threats:\n"
        "• Deep URL safety & destination analysis\n"
        "• QR code scanner with auto-link check\n"
        "• File extension & security inspector\n"
        "• Secure password manager & vault\n\n"
        "<i>Stay safe online.</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

# --- 1. URL SAFETY CHECKER ---
@dp.callback_query(F.data == "tool_url")
async def url_tool_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ToolStates.waiting_for_url)
    text = (
        "<b>[ 🔗 URL SAFETY CHECKER ]</b>\n\n"
        "Send or paste the URL you want to analyze:"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(ToolStates.waiting_for_url, F.text)
async def process_url_check(message: Message, state: FSMContext):
    url = message.text.strip()
    analysis_result = analyze_url_deep(url)
    
    text = (
        f"<b>[ URL DEEP ANALYSIS REPORT ]</b>\n\n"
        f"Input: <code>{url[:50]}...</code>\n\n"
        f"{analysis_result}\n\n"
        f"<i>Always double-check domains before entering credentials.</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Check Another URL", callback_data="tool_url")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()

# --- 2. QR CODE SCANNER (WITH AUTO-LINK CHECK) ---
@dp.callback_query(F.data == "tool_qr")
async def qr_tool_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "<b>[ 📷 QR CODE SCANNER ]</b>\n\n"
        "Send an image containing a QR code as a **Photo**, and I will decode and analyze its contents instantly."
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
            text = "<b>[ ⚠️ QR SCAN RESULT ]</b>\n\nNo QR code detected in this image. Try sending a clearer photo."
        else:
            # Check if decoded data looks like a URL or website
            if "." in qr_data and " " not in qr_data:
                link_analysis = analyze_url_deep(qr_data)
                text = (
                    f"<b>[ ✅ QR CODE DECODED & ANALYZED ]</b>\n\n"
                    f"Raw Content:\n<code>{qr_data}</code>\n\n"
                    f"<b>Destination Analysis:</b>\n{link_analysis}"
                )
            else:
                text = (
                    f"<b>[ ✅ QR CODE DECODED ]</b>\n\n"
                    f"Text Content:\n<code>{qr_data}</code>\n\n"
                    f"<i>Status: Plain text format (Safe).</i>"
                )
    except Exception:
        text = "<b>[ ❌ ERROR ]</b>\n\nCould not process the image. Please try another one."
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# --- 3. FILE INSPECTOR ---
@dp.callback_query(F.data == "tool_file")
async def file_tool_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "<b>[ 🛡 FILE INSPECTOR ]</b>\n\n"
        "Send any file or document, and I will inspect its extension, size, and security risks."
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
    
    risk_level = "Safe Standard Format ✅"
    if ext in dangerous_extensions:
        risk_level = "HIGH RISK ❌ (Executable / Script format)"
    elif ext in warning_extensions:
        risk_level = "Moderate Warning ⚠️ (Compressed container)"
        
    size_mb = round(file_size / (1024 * 1024), 2)
    
    text = (
        f"<b>[ 🛡 FILE INSPECTION REPORT ]</b>\n\n"
        f"• File Name: <code>{file_name}</code>\n"
        f"• Size: <code>{size_mb} MB</code>\n"
        f"• Type: <code>{mime_type}</code>\n"
        f"• Extension: <code>.{ext}</code>\n\n"
        f"<b>Security Assessment:</b>\n"
        f"Status: <b>{risk_level}</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# --- 4. PASSWORD MANAGER & GENERATOR ---
@dp.callback_query(F.data == "tool_pass")
async def password_manager_menu(callback: CallbackQuery):
    text = (
        "<b>[ 🔑 PASSWORD MANAGER ]</b>\n\n"
        "Generate secure passwords or access your saved vault securely:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Generate New Password", callback_data="gen_password")],
        [InlineKeyboardButton(text="📁 View Saved Passwords", callback_data="view_saved_passes")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "gen_password")
async def generate_password_action(callback: CallbackQuery):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = "".join(random.choices(chars, k=16))
    
    text = (
        "<b>[ 🔑 GENERATED PASSWORD ]</b>\n\n"
        f"<code>{password}</code>\n\n"
        "<i>Tap the password to copy, or use options below:</i>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 Save to Vault", callback_data=f"save_pass_{password}"),
         InlineKeyboardButton(text="📤 Send to Chat", callback_data=f"send_pass_{password}")],
        [InlineKeyboardButton(text="🔄 Generate Another", callback_data="gen_password")],
        [InlineKeyboardButton(text="← Password Menu", callback_data="tool_pass")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("save_pass_"))
async def save_password_callback(callback: CallbackQuery):
    password = callback.data.replace("save_pass_", "")
    user_id = callback.from_user.id
    save_password_db(user_id, password)
    await callback.answer("✅ Password successfully saved to your vault!", show_alert=True)

@dp.callback_query(F.data.startswith("send_pass_"))
async def send_password_callback(callback: CallbackQuery):
    password = callback.data.replace("send_pass_", "")
    await callback.message.answer(f"🔑 Here is your password:\n<code>{password}</code>", parser_mode="HTML" if hasattr(Message, 'answer') else None, parse_mode="HTML")
    await callback.answer("Sent to chat!")

@dp.callback_query(F.data == "view_saved_passes")
async def view_saved_passwords(callback: CallbackQuery):
    user_id = callback.from_user.id
    rows = get_saved_passwords_db(user_id)
    
    if not rows:
        text = "<b>[ 📁 SAVED PASSWORDS VAULT ]</b>\n\nYour vault is currently empty."
    else:
        pass_list = "\n".join([f"• <code>{item[0]}</code> — <i>{item[1]}</i>" for item in rows])
        text = f"<b>[ 📁 SAVED PASSWORDS VAULT ]</b>\n\n{pass_list}"
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Password Menu", callback_data="tool_pass")]
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
    
