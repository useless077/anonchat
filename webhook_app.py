import uvicorn
from fastapi import FastAPI, Request
from pyrogram import Client
from config import Config
from handlers import *  # register handlers

app = FastAPI()

pyro = Client(
    "anon-bot",
    bot_token=Config.BOT_TOKEN,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    in_memory=True
)

@app.on_event("startup")
async def startup():
    await pyro.start()
    # Set webhook
    url = f"{Config.WEBHOOK}/webhook/{Config.BOT_TOKEN}"
    await pyro.set_webhook(url)

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
