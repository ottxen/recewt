import os
import asyncio
import random
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# Беремо токен із змінної середовища BOT_TOKEN на Railway
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Error: BOT_TOKEN environment variable is not set!")

router = Router()
logging.basicConfig(level=logging.INFO)

# Сучасні короткі морфеми для унікальної генерації
PREFIXES = ["ax", "ex", "en", "om", "un", "al", "ev", "ix", "ox", "ul"]
ROOTS = ["flux", "vibe", "aura", "shift", "loop", "sync", "pulse", "apex", "zen", "core", "mesh", "flow"]
SUFFIXES = ["ly", "io", "ify", "r", "q", "x", "z"]

class GeneratorStates(StatesGroup):
    waiting_for_mutation_word = State()

def get_main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Direct Search", callback_data="cmd_direct"),
                InlineKeyboardButton(text="🧩 Brand Combine", callback_data="cmd_combine")
            ],
            [
                InlineKeyboardButton(text="⚡ Word Mutate", callback_data="cmd_mutate"),
                InlineKeyboardButton(text="👁 Monitor", callback_data="cmd_monitor")
            ],
            [
                InlineKeyboardButton(text="👤 Profile", callback_data="cmd_profile")
            ]
        ]
    )

def get_back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Back to Menu", callback_data="back_to_menu")]
        ]
    )

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "Welcome to **R3gistry**.\n\n"
        "Your clean space for username intelligence, modern brand combinations, and availability checks. "
        "Choose what you'd like to do below:"
    )
    await message.answer(text, reply_markup=get_main_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "Main Menu. Choose an option:"
    await callback.message.edit_text(text, reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "cmd_direct")
async def mode_direct(callback: CallbackQuery):
    text = (
        "**Direct Search**\n\n"
        "Send me any username or keyword to check its availability right now."
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "cmd_combine")
async def mode_combine(callback: CallbackQuery):
    results = set()
    while len(results) < 5:
        style = random.choice([1, 2, 3])
        if style == 1:
            comb = random.choice(ROOTS) + random.choice(ROOTS)
        elif style == 2:
            comb = random.choice(PREFIXES) + random.choice(ROOTS)
        else:
            comb = random.choice(ROOTS) + random.choice(SUFFIXES)
        results.add(f"• @`{comb}`")
    
    res_text = "\n".join(results)
    text = (
        "**Brand Combinations**\n\n"
        "Here are fresh, dynamically generated options for your project:\n\n"
        f"{res_text}"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Generate More", callback_data="cmd_combine")],
            [InlineKeyboardButton(text="← Back to Menu", callback_data="back_to_menu")]
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "cmd_mutate")
async def mode_mutate_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GeneratorStates.waiting_for_mutation_word)
    text = (
        "**Word Mutator**\n\n"
        "Type any base word (for example: *flow*, *sync*, *core*), and I will generate alternative brand variations for you:"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")

@router.message(GeneratorStates.waiting_for_mutation_word)
async def process_mutation(message: Message, state: FSMContext):
    word = message.text.strip().lower()
    if len(word) < 2:
        await message.answer("That word is a bit too short. Try another one:")
        return

    mutations = [
        f"@{word}r",
        f"@{word}x",
        f"@{word}io",
        f"@{word}ly",
        f"@{word}{word[-1]}",
        f"@z{word}"
    ]
    unique_muts = list(set(mutations))[:6]
    res_text = "\n".join([f"• `{m}`" for m in unique_muts])
    
    text = (
        f"**Variations for '{word}':**\n\n"
        f"{res_text}\n\n"
        "Send another word or head back to the menu:"
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Back to Menu", callback_data="back_to_menu")]
        ]
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "cmd_monitor")
async def mode_monitor(callback: CallbackQuery):
    text = (
        "**Tracking Monitor**\n\n"
        "You have no active trackers right now.\n"
        "Set up alerts to track username releases effortlessly."
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "cmd_profile")
async def mode_profile(callback: CallbackQuery):
    text = (
        "**Your Profile**\n\n"
        f"User ID: `{callback.from_user.id}`\n"
        "Account Status: Standard (Free & Unlimited)"
    )
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="Markdown")
    await callback.answer()

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
