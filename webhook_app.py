# webhook_app.py
import asyncio
from fastapi import FastAPI
from pyrogram import Client
from config import Config

API_ID = Config.API_ID
API_HASH = Config.API_HASH
BOT_TOKEN = Config.BOT_TOKEN

# FastAPI app
app = FastAPI()

pyro = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ---- Lifespan events for FastAPI ----
@app.on_event("startup")
async def startup_event():
    # Start Pyrogram client
    try:
        await pyro.start()
        print("Pyrogram started successfully.")
    except Exception as e:
        print("Failed to start Pyrogram:", e)
        # You can optionally raise here to stop app
        raise e

@app.on_event("shutdown")
async def shutdown_event():
    # Stop Pyrogram client
    await pyro.stop()
    print("Pyrogram stopped.")

# ---- Example webhook route ----
@app.get("/")
async def root():
    return {"status": "ok"}

# ---- Optional: run only if local testing ----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
