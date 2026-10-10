
import asyncio
import aiohttp
import re

API_URL = "https://tg-username-api.vercel.app/api/v1/check"

_check_lock = asyncio.Lock()


async def check_username(username: str) -> str:
    username = username.strip().lstrip("@")

    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{4,31}", username):
        return "invalid"

    async with _check_lock:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    API_URL,
                    params={"username": username},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return "unknown"

                    data = await response.json()

            if not data.get("success"):
                return "unknown"

            result = data.get("result", {})
            status = result.get("status")

            if status == "available":
                return "free"

            if status == "taken":
                return "taken"

            if status == "fragment_collectible":
                return "paid"

            if status == "invalid":
                return "invalid"

            return "unknown"

        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return "unknown"

        finally:
            await asyncio.sleep(2.5)
          
