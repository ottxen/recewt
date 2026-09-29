import asyncio
import datetime
import logging
import os
import sqlite3
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

TOKEN = os.getenv("BOT_TOKEN")

# 👇 Впиши сюди свій власний Telegram ID для тестування команд
TEST_ADMIN_ID = 5619415334

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- БАЗА ДАНИХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            referrals_count INTEGER DEFAULT 0,
            total_invited INTEGER DEFAULT 0,
            premium_until TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, referrer_id, referrals_count, total_invited, premium_until FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def add_user(user_id: int, referrer_id: int = None):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
        conn.commit()
    conn.close()

def update_referral_progress(referrer_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT referrals_count, total_invited, premium_until FROM users WHERE user_id = ?", (referrer_id,))
    row = cursor.fetchone()
    
    if row:
        ref_count, total_inv, prem_until = row
        ref_count += 1
        total_inv += 1
        
        now = datetime.datetime.now()
        current_prem = datetime.datetime.fromisoformat(prem_until) if prem_until and datetime.datetime.fromisoformat(prem_until) > now else now
        
        days_to_add = 0
        reset_scale = False
        
        # Фіксовані нагороди без сумування
        if ref_count == 2:
            days_to_add = 1
        elif ref_count == 3:
            days_to_add = 3
        elif ref_count >= 5:
            days_to_add = 7
            reset_scale = True # Обнуляємо шкалу після досягнення 5 рефералів
            
        new_prem = current_prem + datetime.timedelta(days=days_to_add) if days_to_add > 0 else current_prem
        new_ref_count = 0 if reset_scale else ref_count
        
        cursor.execute("""
            UPDATE users 
            SET referrals_count = ?, total_invited = ?, premium_until = ? 
            WHERE user_id = ?
        """, (new_ref_count, total_inv, new_prem.isoformat(), referrer_id))
        conn.commit()
        
        if days_to_add > 0:
            asyncio.create_task(
                bot.send_message(
                    referrer_id, 
                    f"🎉 **Вітаємо!** Ви досягли цілі реферальної програми та отримали **{days_to_add} дн(ів) Premium-статусу!** 🚀"
                )
            )
    conn.close()

# --- КЛАВІАТУРА ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Premium & Referrals", callback_data="menu_premium")],
        [InlineKeyboardButton(text="🔍 Check Username / Monitor", callback_data="menu_monitor")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_back")]
    ])

# --- ХЕНДЛЕРИ ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
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
        if referrer_id:
            update_referral_progress(referrer_id)

    welcome_text = (
        "✦ ─────────── ⚡ ─────────── ✦\n"
        "         🤖 **TAGTRACK BOT**         \n"
        "✦ ─────────── ⚡ ─────────── ✦\n\n"
        "✨ *Your professional username tracker & monitor.*\n\n"
        "👇 *Choose an option below:*"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# 🧪 ТЕСТОВА КОМАНДА: надішли /addref у чаті з ботом, щоб штучно додати собі реферала
@dp.message(Command("addref"))
async def test_add_referral(message: Message):
    if message.from_user.id != TEST_ADMIN_ID:
        await message.answer("❌ У вас немає прав для використання цієї тестової команди.")
        return
    
    # Переконуємось, що користувач є в базі
    if not get_user(message.from_user.id):
        add_user(message.from_user.id)
        
    # Імітуємо додавання реферала
    update_referral_progress(message.from_user.id)
    user_data = get_user(message.from_user.id)
    
    await message.answer(
        f"🧪 **[ТЕСТ]** Реферала успішно додано!\n"
        f"📊 Поточна шкала: `{user_data[2]}/5`\n"
        f"🌐 Загалом запрошено: `{user_data[3]}`"
    )

@dp.callback_query(F.data == "menu_premium")
async def show_premium_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_data = get_user(user_id)
    
    ref_count = user_data[2] if user_data else 0
    total_invited = user_data[3] if user_data else 0
    prem_until_str = user_data[4] if user_data else None
    
    is_premium = False
    prem_status_text = "❌ Inactive"
    if prem_until_str:
        prem_date = datetime.datetime.fromisoformat(prem_until_str)
        if prem_date > datetime.datetime.now():
            is_premium = True
            prem_status_text = f"✅ Active until {prem_date.strftime('%d.%m.%Y %H:%M')}"

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    text = (
        "✦ ─────────── 💎 ─────────── ✦\n"
        "         **PREMIUM & REFERRALS**         \n"
        "✦ ─────────── ⚡ ─────────── ✦\n\n"
        f"📊 **Status:** {prem_status_text}\n"
        f"👥 **Current scale progress:** `{ref_count}/5`\n"
        f"🌐 **Total invited friends:** `{total_invited}`\n\n"
        "🎁 **Fixed Reward Tiers (Non-cumulative):**\n"
        " • 2 referrals ➔ ➕ **1 day** Premium\n"
        " • 3 referrals ➔ ➕ **3 days** Premium\n"
        " • 5 referrals ➔ ➕ **7 days** Premium *(Scale resets)*\n\n"
        "🔗 **Your Referral Link:**\n"
        f"`{ref_link}`\n\n"
        "💡 *Rewards are fixed per tier and do not stack with previous steps!*"
    )
    
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "menu_monitor")
async def show_monitor_menu(callback: CallbackQuery):
    text = (
        "✦ ─────────── 🔍 ─────────── ✦\n"
        "         **USERNAME MONITOR**         \n"
        "✦ ─────────── ⚡ ─────────── ✦\n\n"
        "📝 *Send the username you want to track.* \n\n"
        "⚠️ *Free users have 1 slot limit. Premium users get up to 5-10 slots and automatic instant tracking!*"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "menu_back")
async def back_to_main(callback: CallbackQuery):
    welcome_text = (
        "✦ ─────────── ⚡ ─────────── ✦\n"
        "         🤖 **TAGTRACK BOT**         \n"
        "✦ ─────────── ⚡ ─────────── ✦\n\n"
        "✨ *Your professional username tracker & monitor.*\n\n"
        "👇 *Choose an option below:*"
    )
    await callback.message.edit_text(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    await callback.answer()

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("TagTrack Bot is online with test tools!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
