from config import Config
from pyrogram import Client
from handlers import *  # registers handlers

pyro = Client(
    "anon_chat_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    sleep_threshold=0  # <- add this
)

print("🚀 Bot starting...")
app.run()
