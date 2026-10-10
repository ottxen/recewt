
import asyncio
import logging
import random
import re

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

MAX_SEARCH_ATTEMPTS = 20
PAGE_SIZE = 10

DEFAULT_WORDS = [
    "official", "support", "admin", "developer",
    "security", "manager", "digital", "network",
    "service", "system", "email", "database",
    "account", "technology", "software",
    "telegram", "registry", "username", "profile",
    "information",
]

# Search results are kept in memory until the bot restarts.
search_sessions = {}
watch_task = None


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

    if words:
        word = re.sub(
            r"[^a-zA-Z0-9]", "", random.choice(words)
        ).lower()

        if not word:
            word = "user"

        if not word[0].isalpha():
            word = "user" + word

        word = word[:30]

        minimum = max(12, len(word))
        if underscore == "with":
            minimum = max(minimum, len(word) + 1)
        if digits == "with" and not any(c.isdigit() for c in word):
            minimum = max(minimum, len(word) + 1)

        target = random.randint(minimum, min(32, max(minimum, 16)))
        target = min(32, max(target, len(word)))

        username = word

        while len(username) < target:
            username += random.choice(alphabet)

        if underscore == "with" and "_" not in username:
            username = username[:1] + "_" + username[2:]

        elif underscore == "either" and random.random() < 0.35:
            position = random.randrange(1, len(username))
            username = username[:position] + "_" + username[position + 1:]

        if digits == "with" and not any(c.isdigit() for c in username):
            position = random.randrange(1, len(username))
            username = (
                username[:position]
                + random.choice("0123456789")
                + username[position + 1:]
            )

        return username

    length = int(length)
    chars = [random.choice("abcdefghijklmnopqrstuvwxyz")]

    chars.extend(
        random.choice(alphabet)
        for _ in range(length - 1)
    )

    if digits == "with" and not any(c.isdigit() for c in chars):
        pos = random.randrange(1, length)
        chars[pos] = random.choice("0123456789")

    if underscore == "with":
        pos = random.randrange(1, length)
        chars[pos] = "_"
    elif underscore == "either" and random.random() < 0.35:
        pos = random.randrange(1, length)
        chars[pos] = "_"

    return "".join(chars)


def length_keyboard():
    rows = [
        [
            InlineKeyboardButton(
                text=f"{n} characters",
                callback_data=f"len:{n}"
            )
        ]
        for n in range(5, 9)
    ]

    rows.append([
        InlineKeyboardButton(
            text="12+ characters",
            callback_data="len:12plus"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def digits_keyboard():
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


def words_keyboard(selected):
    rows = []

    for start in range(0, len(DEFAULT_WORDS), 2):
        row = []

        for word in DEFAULT_WORDS[start:start + 2]:
            mark = "✅ " if word in selected else ""
            row.append(InlineKeyboardButton(
                text=mark + word,
                callback_data=f"kw:{word}"
            ))

        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            text=f"🔎 Search ({len(selected)}/3 selected)",
            callback_data="kw:done"
        )
    ])

    rows.append([
        InlineKeyboardButton(
            text="❌ Clear selection",
            callback_data="kw:clear"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def results_keyboard(user_id: int, page: int, total: int):
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    rows = []

    nav = []

    if page > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️ Previous",
            callback_data="page:prev"
        ))

    nav.append(InlineKeyboardButton(
        text=f"{page + 1}/{pages}",
        callback_data="page:info"
    ))

    if page < pages - 1:
        nav.append(InlineKeyboardButton(
            text="Next ➡️",
            callback_data="page:next"
        ))

    rows.append(nav)
    rows.append([
        InlineKeyboardButton(
            text="🔄 New search",
            callback_data="search"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_results(message: Message, user_id: int, page: int = 0):
    session = search_sessions.get(user_id)

    if not session:
        await message.answer(
            "Search results expired. Please start a new search."
        )
        return

    results = session["results"]
    total = len(results)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    page = max(0, min(page, pages - 1))
    session["page"] = page

    start = page * PAGE_SIZE
    current = results[start:start + PAGE_SIZE]

    text = (
        "🟢 Potentially available usernames\n\n"
        + "\n".join(current)
        + f"\n\nPage {page + 1}/{pages}"
        + f"\nTotal results: {total}"
        + "\n\nAvailability is not guaranteed. "
        "Verify usernames directly in Telegram."
    )

    keyboard = results_keyboard(user_id, page, total)

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(
            text,
            reply_markup=keyboard
        )
    else:
        await message.answer(text, reply_markup=keyboard)


async def perform_search(
    message: Message,
    user_id: int,
    length: str,
    digits: str = "either",
    underscore: str = "either",
    words=None,
):
    words = words or []

    premium = await db.is_premium(user_id)
    result_limit = 20 if premium else 10

    progress = await message.answer(
        "🔎 Searching for usernames...\n"
        f"Maximum checks: {MAX_SEARCH_ATTEMPTS}\n"
        "This may take a little while."
    )

    found = []
    checked = set()

    for _ in range(MAX_SEARCH_ATTEMPTS):
        if len(found) >= result_limit:
            break

        if length == "12plus":
            random_length = random.randint(12, 16)
            username = make_username(
                random_length, digits, underscore, words
            )
        else:
            username = make_username(
                int(length), "either", "either", []
            )

        if username in checked:
            continue

        checked.add(username)

        try:
            status = await asyncio.wait_for(
                check_username(username),
                timeout=35,
            )
        except Exception:
            logging.exception("Username check failed")
            continue

        if status == "free":
            found.append(f"🟢 @{username}")

    if found:
        search_sessions[user_id] = {
            "results": found,
            "page": 0,
        }

        text = (
            "🟢 Search completed!\n"
            f"Found: {len(found)} potentially available username(s).\n"
            "Preparing results..."
        )

        await progress.edit_text(text)
        await show_results(progress, user_id, 0)

    else:
        await progress.edit_text(
            "No usernames could be verified as available.\n\n"
            "Try another search. The checking service may also "
            "be temporarily unavailable.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔄 Try again",
                    callback_data="search"
                )]
            ])
        )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()

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


@dp.callback_query(F.data == "search")
async def choose_length(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    await callback.message.answer(
        "Choose username length:",
        reply_markup=length_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("len:"))
async def choose_length_result(
    callback: CallbackQuery,
    state: FSMContext,
):
    length = callback.data.split(":", 1)[1]
    await callback.answer()

    if length in {"5", "6", "7", "8"}:
        await state.clear()

        # Short username searches start immediately.
        await perform_search(
            callback.message,
            callback.from_user.id,
            length,
        )
        return

    if length == "12plus":
        await state.update_data(length=length)
        await callback.message.answer(
            "Should usernames contain numbers?",
            reply_markup=digits_keyboard(),
        )


@dp.callback_query(F.data.startswith("digits:"))
async def choose_digits(
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
async def choose_underscore(
    callback: CallbackQuery,
    state: FSMContext,
):
    underscore = callback.data.split(":", 1)[1]

    await state.update_data(underscore=underscore, words=[])
    await state.set_state(InputState.search_words)

    await callback.message.answer(
        "Choose up to 3 keywords.\n"
        "Tap a word to select or deselect it.\n\n"
        "You can also continue without selecting any words.",
        reply_markup=words_keyboard([]),
    )
    await callback.answer()


@dp.callback_query(
    InputState.search_words,
    F.data.startswith("kw:")
)
async def select_keywords(
    callback: CallbackQuery,
    state: FSMContext,
):
    action = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = list(data.get("words", []))

    if action == "clear":
        selected = []

    elif action == "done":
        await callback.answer("Starting search...")
        length = data.get("length", "12plus")
        digits = data.get("digits", "either")
        underscore = data.get("underscore", "either")

        await state.clear()

        await perform_search(
            callback.message,
            callback.from_user.id,
            length,
            digits,
            underscore,
            selected,
        )
        return

    elif action in DEFAULT_WORDS:
        if action in selected:
            selected.remove(action)
        elif len(selected) < 3:
            selected.append(action)
        else:
            await callback.answer(
                "You can select up to 3 keywords.",
                show_alert=True,
            )
            return

    await state.update_data(words=selected)

    await callback.message.edit_reply_markup(
        reply_markup=words_keyboard(selected)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("page:"))
async def change_page(callback: CallbackQuery):
    user_id = callback.from_user.id
    session = search_sessions.get(user_id)

    if not session:
        await callback.answer(
            "Results expired. Start a new search.",
            show_alert=True,
        )
        return

    action = callback.data.split(":", 1)[1]
    page = session["page"]

    if action == "prev":
        page -= 1
    elif action == "next":
        page += 1
    elif action == "info":
        await callback.answer(
            f"Page {page + 1}"
        )
        return

    await callback.answer()
    await show_results(callback, user_id, page)


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

    username = username.lower()

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
                        timeout=35,
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
    global watch_task

    await db.init_db()
    watch_task = asyncio.create_task(watch_loop())
    logging.info("R3GISTRY started successfully")


async def on_shutdown():
    global watch_task

    if watch_task:
        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass

    await db.close_db()
    await bot.session.close()


dp.startup.register(on_startup)
dp.shutdown.register(on_shutdown)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    
