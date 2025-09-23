# app.py
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pyrogram import Client
from pyrogram.storage.mongo_storage import MongoStorage
from config import Config
from bot import register_handlers  # your chat handlers

# Use MongoDB for Pyrogram session storage
storage = MongoStorage(Config.MONGO_URI, Config.DB_NAME, "sessions")

bot = Client(
    "anon_chat_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    storage=storage
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.start()
    print("Bot started with MongoDB session storage")
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
