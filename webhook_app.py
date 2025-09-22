from fastapi import FastAPI
from pyrogram import Client
from config import Config

app = FastAPI()
pyro = Client(
    "anon_chat_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
)

# Lifespan event handler (replaces on_event)
@app.on_event("startup")
async def startup_event():
    await pyro.start()
    print("Bot started!")

@app.on_event("shutdown")
async def shutdown_event():
    await pyro.stop()
    print("Bot stopped!")

@app.get("/")
async def root():
    return {"status": "Bot is running"}
