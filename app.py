
import asyncio
import random
import re
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

import config
import db
from checker import check_username

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()


class InputState(StatesGroup):
    check_username = State()
    watch_username = State()


def menu(user_id: int):
    rows = [
        [InlineKeyboardButton(
            text="🔎 Check username",
            callback_data="check"
        )],
        [InlineKeyboardButton(
            text="🎲 Find usernames",
            callback_data="search"
        )],
        [InlineKeyboardButton(
            text="👁 Watch a username",
            callback_data="watch"
        )],
        [InlineKeyboardButton(
            text="📋 My watchlist",
            callback_data="my_watches"
        )],
    ]

    if user_id in config.ADMIN_IDS:
        rows.append([InlineKeyboardButton(
            text="⚙️ Admin panel",
            callback_data="admin"
        )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def valid_username(value: str) -> bool:
    value = value.lstrip("@")
    return bool(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", value)
    )


async def status_text(username: str) -> str:
    status = await checker.check(username)

    if status == "free":
        return f"🟢 @{username} — potentially available."
    if status == "taken":
        return f"🔴 @{username} — taken."
    if status == "invalid":
        return f"⚠️ @{username} — invalid username."
    return f"❔ @{username} — status unknown."


@dp.message(CommandStart())
async def start(message: Message):
    await db.add_user(
        message.from_user.id,
        message.from_user.username,
    )

    await message.answer(
        "⟡ R3GISTRY\n\n"
        "Search and monitor Telegram usernames.\n"
        "Choose an option below:",
        reply_markup=menu(message.from_user.id),
    )


@dp.callback_query(F.data == "check")
async def ask_check(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(InputState.check_username)
    await callback.message.answer(
        "Send a username to check, for example: @example"
    )
    await callback.answer()


@dp.message(InputState.check_username)
async def do_check(message: Message, state: FSMContext):
    username = (
        message.text.strip().lstrip("@")
        if message.text else ""
    )
    await state.clear()

    if not valid_username(username):
        await message.answer(
            "Invalid username format. Use 5–32 characters, "
            "start with a letter, and use only letters, "
            "numbers, or underscores."
        )
        return

    await message.answer("Checking username...")
    await message.answer(await status_text(username))


@dp.callback_query(F.data == "search")
async def choose_length(callback: CallbackQuery):
    buttons = [
        InlineKeyboardButton(
            text=f"{length} characters",
            callback_data=f"len:{length}",
        )
        for length in range(5, 13)
    ]

    rows = [
        buttons[i:i + 2]
        for i in range(0, len(buttons), 2)
    ]

    await callback.message.answer(
        "Choose the username length:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=rows
        ),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("len:"))
async def search_names(callback: CallbackQuery):
    length = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    limit = 3 if await db.is_premium(user_id) else 1
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"

    await callback.message.answer(
        f"Generating usernames with {length} characters..."
    )

    candidates = set()

    while len(candidates) < limit:
        first = random.choice("abcdefghijklmnopqrstuvwxyz")
        rest = "".join(
            random.choice(alphabet)
            for _ in range(length - 1)
        )
        candidates.add(first + rest)

    results = []

    for username in candidates:
        results.append(await status_text(username))

    await callback.message.answer("\n".join(results))
    await callback.answer()


@dp.callback_query(F.data == "watch")
async def ask_watch(
    callback: CallbackQuery,
    state: FSMContext,
):
    await state.set_state(InputState.watch_username)
    await callback.message.answer(
        "Send the username you want to monitor."
    )
    await callback.answer()


@dp.message(InputState.watch_username)
async def do_watch(message: Message, state: FSMContext):
    username = (
        message.text.strip().lstrip("@")
        if message.text else ""
    )
    await state.clear()

    if not valid_username(username):
        await message.answer("Invalid username format.")
        return

    await db.add_watch(message.from_user.id, username)

    await message.answer(
        f"👁 @{username} has been added to your watchlist.\n"
        "I'll notify you if a check indicates it may be available."
    )


@dp.callback_query(F.data == "my_watches")
async def my_watches(callback: CallbackQuery):
    rows = await db.get_user_watches(callback.from_user.id)

    if not rows:
        text = "Your watchlist is currently empty."
    else:
        text = "📋 Your watchlist:\n\n" + "\n".join(
            f"@{row['username']}" for row in rows
        )
        text += (
            "\n\nTo remove a username, use:\n"
            "/unwatch username"
        )

    await callback.message.answer(text)
    await callback.answer()


@dp.message(Command("unwatch"))
async def unwatch(message: Message):
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "Usage: /unwatch username"
        )
        return

    username = parts[1].strip().lstrip("@").lower()
    removed = await db.remove_watch(
        message.from_user.id,
        username,
    )

    await message.answer(
        "Watch removed."
        if removed else "Active watch not found."
    )


@dp.callback_query(F.data == "admin")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer(
            "Access denied.",
            show_alert=True,
        )
        return

    users, premium, watches = await db.get_stats()

    await callback.message.answer(
        "⚙️ R3GISTRY ADMIN PANEL\n\n"
        f"Total users: {users}\n"
        f"Premium users: {premium}\n"
        f"Active watches: {watches}\n\n"
        "Grant Premium: /premium USER_ID\n"
        "Revoke Premium: /unpremium USER_ID"
    )
    await callback.answer()


@dp.message(Command("premium"))
async def grant_premium(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    parts = (message.text or "").split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            "Usage: /premium USER_ID"
        )
        return

    await db.set_premium(int(parts[1]), True)
    await message.answer("Premium has been enabled.")


@dp.message(Command("unpremium"))
async def revoke_premium(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    parts = (message.text or "").split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            "Usage: /unpremium USER_ID"
        )
        return

    await db.set_premium(int(parts[1]), False)
    await message.answer("Premium has been disabled.")


async def watch_loop():
    while True:
        try:
            watches = await db.get_pending_watches()

            for watch in watches:
                status = await checker.check(watch["username"])

                if status == "free":
                    try:
                        await bot.send_message(
                            watch["user_id"],
                            f"🟢 @{watch['username']} may be available!\n"
                            "Please verify its status directly in "
                            "Telegram. Availability is not guaranteed."
                        )
                        await db.mark_notified(watch["id"])
                    except Exception:
                        logging.exception(
                            "Failed to send availability notification"
                        )

        except Exception:
            logging.exception("Error in the watch loop")

        await asyncio.sleep(600)


async def on_startup():
    await db.init_db()
    await checker.start()
    asyncio.create_task(watch_loop())
    logging.info("R3GISTRY started successfully")


async def on_shutdown():
    await checker.stop()
    await db.close_db()


dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
  
