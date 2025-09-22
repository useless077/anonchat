import uvicorn
from fastapi import FastAPI, Request
from pyrogram import Client
from config import Config
from handlers import *  # register handlers

app = FastAPI()

pyro = Client(
    "anon_chat_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    sleep_threshold=0
)

@app.on_event("startup")
async def startup():
    await pyro.start()

@app.on_event("shutdown")
async def shutdown():
    await pyro.stop()

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != Config.BOT_TOKEN:
        return {"status": "forbidden"}
    data = await request.json()
    await pyro.process_updates([data])
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run("webhook_app:app", host="0.0.0.0", port=Config.PORT)
