# app.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pyrogram import Client
from config import Config
from db import MongoStorage, sessions
from bot import register_handlers

# Mongo storage for Pyrogram
storage = MongoStorage(sessions)

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
    print("Bot started")
    register_handlers(bot)
    try:
        yield
    finally:
        await bot.stop()
        await storage.close()
        print("Bot stopped")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "Bot is alive"}
