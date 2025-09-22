from pyrogram import Client
from config import Config
import asyncio

bot = Client(
    "anon_chat_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    sleep_threshold=60,   # handle minor clock drift
    workers=4,
)

async def main():
    await bot.start()
    print("Bot started!")
    # Keep the bot running forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
