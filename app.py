from pyrogram import Client
from bot import start_bot
from config import API_ID, API_HASH, BOT_TOKEN

app = Client("anonchat", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Start the bot features
start_bot(app)

print("AnonChat Bot is running...")
app.run()
