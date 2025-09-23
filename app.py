# app.py (rename webhook_app or use this)
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pyrogram import Client
from pyrogram import raw
from config import Config
from handlers import register_handlers  # or import needed handler functions

# Setup Telegram client
bot = Client(
    "anon_chat_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    sleep_threshold=60,  # helps with small clock drift
)

async def sync_time(bot: Client):
    try:
        await bot.invoke(raw.functions.Help.GetConfig())
        print("Time sync done")
    except Exception as e:
        print("Time sync failed:", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.start()
    print("Bot started")
    await sync_time(bot)
    # register handlers
    register_handlers(bot)
    try:
        yield
    finally:
        await bot.stop()
        print("Bot stopped")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "Bot is alive"}

# If you have other webhook routes or health checks, define here
# No need for if __name__ == "__main__" when deploying via Procfile or Docker
