import asyncio
import datetime
import logging
import os
import random
import string
import sys
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

# Вбудований у OpenCV детектор QR-кодів (не потребує сторонніх системних бібліотек)
import cv2

TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- FSM STATES ---
class ToolStates(StatesGroup):
    waiting_for_url = State()

# --- MAIN KEYBOARD ---
def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Check URL Safety", callback_data="tool_url"),
         InlineKeyboardButton(text="📷 Scan QR Code", callback_data="tool_qr")],
        [InlineKeyboardButton(text="🛡 File Inspector", callback_data="tool_file"),
         InlineKeyboardButton(text="🔑 Password Generator", callback_data="tool_pass")],
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
        "• URL safety & tracker removal\n"
        "• QR code scanner & decoder\n"
        "• File extension & metadata inspector\n"
        "• Secure password generator\n\n"
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
    
    suspicious_keywords = ["login", "verify", "update", "secure", "account", "banking", "free", "gift"]
    parsed_lower = url.lower()
    
    is_suspicious = any(kw in parsed_lower for kw in suspicious_keywords) and ("http://" in parsed_lower or len(url) > 50)
    clean_url = url.split("?")[0]
    
    status_icon = "⚠️ Suspicious / Review Required" if is_suspicious else "✅ Clean & Safe Structure"
    
    text = (
        f"<b>[ URL ANALYSIS REPORT ]</b>\n\n"
        f"Target: <code>{url[:60]}...</code>\n"
        f"Status: <b>{status_icon}</b>\n\n"
        f"<b>Details:</b>\n"
        f"• Protocol: <code>{'HTTPS (Secure)' if 'https://' in parsed_lower else 'HTTP (Insecure ⚠️)'}</code>\n"
        f"• Clean URL (No Trackers): <code>{clean_url}</code>\n\n"
        f"<i>Tip: Always verify the exact domain spelling before entering personal data.</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Check Another URL", callback_data="tool_url")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()

# --- 2. QR CODE SCANNER (PHOTO INPUT) ---
@dp.callback_query(F.data == "tool_qr")
async def qr_tool_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "<b>[ 📷 QR CODE SCANNER ]</b>\n\n"
        "Send an image containing a QR code as a **Photo**, and I will decode and check it instantly."
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
            text = (
                f"<b>[ ✅ QR CODE DECODED ]</b>\n\n"
                f"Content found:\n<code>{qr_data}</code>\n\n"
                f"<i>If this is a website link, make sure to verify its safety before opening!</i>"
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
        "Send any file or document, and I will inspect its extension, size, and potential security risks."
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
        risk_level = "Moderate Warning ⚠️ (Compressed or macro-enabled container)"
        
    size_mb = round(file_size / (1024 * 1024), 2)
    
    text = (
        f"<b>[ 🛡 FILE INSPECTION REPORT ]</b>\n\n"
        f"• File Name: <code>{file_name}</code>\n"
        f"• Size: <code>{size_mb} MB</code>\n"
        f"• Type (MIME): <code>{mime_type}</code>\n"
        f"• Extension: <code>.{ext}</code>\n\n"
        f"<b>Security Assessment:</b>\n"
        f"Status: <b>{risk_level}</b>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

# --- 4. PASSWORD GENERATOR ---
@dp.callback_query(F.data == "tool_pass")
async def password_generator(callback: CallbackQuery):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = "".join(random.choices(chars, k=16))
    
    text = (
        "<b>[ 🔑 SECURE PASSWORD GENERATOR ]</b>\n\n"
        "Here is your strong generated password (16 characters):\n\n"
        f"<code>{password}</code>\n\n"
        "<i>Tap the password above to copy it safely.</i>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Generate Another", callback_data="tool_pass")],
        [InlineKeyboardButton(text="← Main Menu", callback_data="menu_back")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

async def main():
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
    
