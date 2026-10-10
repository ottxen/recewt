
import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()


async def main():
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]

    async with TelegramClient(
        StringSession(),
        api_id,
        api_hash,
    ) as client:
        session = StringSession.save(client.session)

        print("\nYour SESSION_STRING:\n")
        print(session)
        print(
            "\nStore it in Railway Variables. "
            "Never publish it or share it with anyone."
        )


if __name__ == "__main__":
    asyncio.run(main())
  
