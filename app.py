
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

MAX_SEARCH_ATTEMPTS = 8

DEFAULT_WORDS = [
    "information", "official", "manager", "email",
    "admin", "support", "system", "developer",
    "security", "database", "network", "service",
    "account", "digital", "technology", "software",
    "telegram", "registry", "username", "profile",
]


class InputState(StatesGroup):
    watch_username = State()
    search_words = State()


def menu(user_id: int):
    rows = [
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
    value = value.strip().lstrip("@")
    return bool(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", value)
    )


def make_username(length, digits, underscore, words):
    alphabet = "abcdefghijklmnopqrstuvwxyz"

    if digits != "without":
        alphabet += "0123456789"

    # Word-based usernames are always at least 12 characters.
    if words:
        word = random.choice(words).lower()
        word = re.sub(r"[^a-z0-9]", "", word)

        if not word:
            word = "user"

        if not word[0].isalpha():
            word = random.choice("abcdefghijklmnopqrstuvwxyz") + word

        word = word[:31]

        extra = 1 if underscore == "with" else 0

        if digits == "with" and not any(
            c.isdigit() for c in word
        ):
            extra = max(extra, 1)

        target = min(32, max(12, len(word) + extra))

        remaining = target - len(word)
        filler = [
            random.choice(alphabet)
            for _ in range(remaining)
        ]

        if underscore == "with" and remaining > 0:
            filler[0] = "_"
        elif underscore == "either" and remaining > 0:
            if random.random() < 0.35:
                filler[random.randrange(remaining)] = "_"

        if digits == "with" and not any(
            c.isdigit() for c in word + "".join(filler)
        ):
            positions = [
                i for i, char in enumerate(filler)
                if char != "_"
            ]
            if positions:
                filler[random.choice(positions)] = random.choice(
                    "0123456789"
                )

        return word + "".join(filler)

    # Random short usernames, 5–8 characters.
    length = int(length)
    chars = [
        random.choice("abcdefghijklmnopqrstuvwxyz")
    ]

    chars.extend(
        random.choice(alphabet)
        for _ in range(length - 1)
    )

    if digits == "with" and not any(
        c.isdigit() for c in chars
    ):
        positions = list(range(1, length))
        chars[random.choice(positions)] = random.choice(
            "0123456789"
        )

    if underscore == "with":
        chars[random.randrange(1, length)] = "_"
    elif underscore == "either" and random.random() < 0.35:
        chars[random.randrange(1, length)] = "_"

    return "".join(chars)


def settings_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Without numbers",
                callback_data="digits:without"
            ),
            InlineKeyboardButton(
                text="With numbers",
                callback_data="digits:with"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Doesn't matter",
                callback_data="digits:either"
            )
        ],
    ])


def underscore_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Without _",
                callback_data="under:without"
            ),
            InlineKeyboardButton(
                text="With _",
                callback_data="under:with"
            ),
        ],
        [
            InlineKeyboardButton(
                text="Doesn't matter",
                callback_data="under:either"
            )
        ],
    ])


@dp.message(CommandStart())
async def start(message: Message):
    await db.add_user(
        message.from_user.id,
        message.from_user.username,
    )

    await message.answer(
        "⟡ R3GISTRY\n\n"
        "Telegram Username Finder\n\n"
        "Generate usernames and monitor names "
        "that may become available.\n\n"
        "Choose an option:",
        reply_markup=menu(message.from_user.id),
    )


# Search flow: select a length.
@dp.callback_query(F.data == "search")
async def choose_length(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    buttons = [
        InlineKeyboardButton(
            text=f"{n} characters",
            callback_data=f"len:{n}"
        )
        for n in range(5, 9)
    ]

    rows = [[button] for button in buttons]

    rows.append([
        InlineKeyboardButton(
            text="12+ characters (word-based)",
            callback_data="len:12plus"
        )
    ])

    await callback.message.answer(
        "Choose your username type:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=rows
        ),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("len:"))
async def choose_numbers(
    callback: CallbackQuery,
    state: FSMContext,
):
    length = callback.data.split(":", 1)[1]

    await state.update_data(length=length)

    await callback.message.answer(
        "Should usernames contain numbers?",
        reply_markup=settings_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("digits:"))
async def choose_underscore(
    callback: CallbackQuery,
    state: FSMContext,
):
    digits = callback.data.split(":", 1)[1]

    await state.update_data(digits=digits)

    await callback.message.answer(
        "Should usernames contain underscores (_)?",
        reply_markup=underscore_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("under:"))
async def ask_words(
    callback: CallbackQuery,
    state: FSMContext,
):
    underscore = callback.data.split(":", 1)[1]

    await state.update_data(underscore=underscore)
    await state.set_state(InputState.search_words)

    await callback.message.answer(
        "Enter required words separated by commas.\n\n"
        "Examples: information, official, manager, "
        "email, admin, developer, security\n\n"
        "Word-based usernames will be at least "
        "12 characters long.\n\n"
        "Send - to use random usernames without required words."
    )
    await callback.answer()


@dp.message(InputState.search_words)
async def run_search(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    raw_words = (message.text or "").strip()

    if raw_words == "-":
        words = []
    elif raw_words:
        words = [
            re.sub(r"[^a-zA-Z0-9]", "", item).lower()
            for item in raw_words.split(",")
        ]
        words = [
            word for word in words
            if word and len(word) <= 30
        ]

        if not words:
            await message.answer(
                "No valid words found. Please try again."
            )
            return
    elif data.get("length") == "12plus":
        words = []
    else:
        words = []

    length = data.get("length", "5")
    digits = data.get("digits", "either")
    underscore = data.get("underscore", "either")

    user_id = message.from_user.id
    limit = 3 if await db.is_premium(user_id) else 1

    await message.answer(
        f"Searching for usernames...\n"
        f"Maximum checks: {MAX_SEARCH_ATTEMPTS}\n"
        "Only positively verified available results will be shown."
    )

    found = []
    checked = set()

    for _ in range(MAX_SEARCH_ATTEMPTS):
        if len(found) >= limit:
            break

        use_words = words

        if length == "12plus" and not use_words:
            use_words = []

        if use_words:
            username = make_username(
                12, digits, underscore, use_words
            )
        elif length == "12plus":
            random_length = random.randint(12, 16)
            username = make_username(
                random_length, digits, underscore, []
            )
        else:
            username = make_username(
                int(length), digits, underscore, []
            )

        if username in checked:
            continue

        checked.add(username)

        try:
            status = await asyncio.wait_for(
                check_username(username),
                timeout=12,
            )
        except (asyncio.TimeoutError, Exception):
            logging.exception("Username check failed")
            continue

        # Never display taken, paid, invalid or unknown names.
        if status == "free":
            found.append(f"🟢 @{username}")

    if found:
        await message.answer(
            "Potentially available usernames:\n\n"
            + "\n".join(found)
            + "\n\nAvailability is not guaranteed. "
            "Verify before trying to claim a username."
        )
    else:
        await message.answer(
            "No usernames could be verified as available "
            "in this search.\n\n"
            "Try different words or settings."
        )

    await message.answer(
        "What would you like to do next?",
        reply_markup=menu(user_id),
    )


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

    await db.add_watch(message.from_user.id, username.lower())

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
        text += "\n\nRemove a username with /unwatch username"

    await callback.message.answer(text)
    await callback.answer()


@dp.message(Command("unwatch"))
async def unwatch(message: Message):
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) != 2:
        await message.answer("Usage: /unwatch username")
        return

    username = parts[1].strip().lstrip("@").lower()
    removed = await db.remove_watch(
        message.from_user.id,
        username,
    )

    await message.answer(
        "Watch removed." if removed else "Active watch not found."
    )


@dp.callback_query(F.data == "admin")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("Access denied.", show_alert=True)
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
        await message.answer("Usage: /premium USER_ID")
        return

    await db.set_premium(int(parts[1]), True)
    await message.answer("Premium has been enabled.")


@dp.message(Command("unpremium"))
async def revoke_premium(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return

    parts = (message.text or "").split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /unpremium USER_ID")
        return

    await db.set_premium(int(parts[1]), False)
    await message.answer("Premium has been disabled.")


async def watch_loop():
    while True:
        try:
            watches = await db.get_pending_watches()

            for watch in watches:
                try:
                    status = await asyncio.wait_for(
                        check_username(watch["username"]),
                        timeout=12,
                    )

                    if status == "free":
                        await bot.send_message(
                            watch["user_id"],
                            f"🟢 @{watch['username']} may be available!\n"
                            "Please verify directly in Telegram."
                        )
                        await db.mark_notified(watch["id"])

                except Exception:
                    logging.exception(
                        "Failed to check or notify watched username"
                    )

        except Exception:
            logging.exception("Error in the watch loop")

        await asyncio.sleep(600)


async def on_startup():
    await db.init_db()
    asyncio.create_task(watch_loop())
    logging.info("R3GISTRY started successfully")


async def on_shutdown():
    await db.close_db()
    await bot.session.close()


dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    
