
import asyncpg
from config import DATABASE_URL

pool = None


async def init_db():
    global pool

    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    pool = await asyncpg.create_pool(
        url,
        min_size=1,
        max_size=5,
        command_timeout=30,
    )

    async with pool.acquire() as con:
        await con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                is_premium BOOLEAN NOT NULL DEFAULT FALSE,
                joined_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS watches (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(user_id)
                    ON DELETE CASCADE,
                username TEXT NOT NULL,
                notified BOOLEAN NOT NULL DEFAULT FALSE,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, username)
            );
        """)


async def close_db():
    if pool:
        await pool.close()


async def add_user(user_id: int, username: str | None):
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO users(user_id, username)
            VALUES($1, $2)
            ON CONFLICT(user_id)
            DO UPDATE SET username = EXCLUDED.username
        """, user_id, username)


async def is_premium(user_id: int) -> bool:
    async with pool.acquire() as con:
        value = await con.fetchval(
            "SELECT is_premium FROM users WHERE user_id = $1",
            user_id,
        )
    return bool(value)


async def set_premium(user_id: int, enabled: bool):
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO users(user_id, is_premium)
            VALUES($1, $2)
            ON CONFLICT(user_id)
            DO UPDATE SET is_premium = EXCLUDED.is_premium
        """, user_id, enabled)


async def get_stats():
    async with pool.acquire() as con:
        users = await con.fetchval(
            "SELECT COUNT(*) FROM users"
        )
        premium = await con.fetchval(
            "SELECT COUNT(*) FROM users WHERE is_premium = TRUE"
        )
        watches = await con.fetchval(
            "SELECT COUNT(*) FROM watches WHERE active = TRUE"
        )

    return users, premium, watches


async def add_watch(user_id: int, username: str):
    async with pool.acquire() as con:
        await con.execute("""
            INSERT INTO watches(user_id, username)
            VALUES($1, $2)
            ON CONFLICT(user_id, username)
            DO UPDATE SET active = TRUE, notified = FALSE
        """, user_id, username.lower())


async def get_user_watches(user_id: int):
    async with pool.acquire() as con:
        return await con.fetch("""
            SELECT username FROM watches
            WHERE user_id = $1 AND active = TRUE
            ORDER BY created_at DESC
        """, user_id)


async def get_pending_watches():
    async with pool.acquire() as con:
        return await con.fetch("""
            SELECT id, user_id, username
            FROM watches
            WHERE active = TRUE AND notified = FALSE
            ORDER BY id
        """)


async def mark_notified(watch_id: int):
    async with pool.acquire() as con:
        await con.execute("""
            UPDATE watches
            SET notified = TRUE
            WHERE id = $1
        """, watch_id)


async def remove_watch(user_id: int, username: str):
    async with pool.acquire() as con:
        result = await con.execute("""
            UPDATE watches
            SET active = FALSE
            WHERE user_id = $1
              AND username = $2
              AND active = TRUE
        """, user_id, username.lower())

    return result.endswith("1")
  
