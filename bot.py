# main.py

import logging
import sys
import asyncio
from pyrogram import Client
from aiohttp import web
from config import API_ID, API_HASH, BOT_TOKEN, PORT, LOG_CHANNEL
from database.users import Database
from plugins.web_support import web_server

# ✅ CORRECT IMPORT: We need the function that STARTS the scheduler
from plugins.ai import load_ai_state, start_greeting_task
from utils import load_autodelete_state # Assuming you moved the function here

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)


# ------------------------------------
# 🤖 BOT CLASS
# ------------------------------------
class Bot(Client):
    def __init__(self):
        super().__init__(
            name="AnonChatBot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5,
        )
        self.database = Database(MONGO_URI, MONGO_DB_NAME) 

    async def start(self):
        try:
            await self.database.connect()
            await super().start()
            me = await self.get_me()
            self.mention = me.mention
            self.username = me.username

            start_message = f"{me.first_name} ✅✅ BOT started successfully ✅✅"
            logging.info(start_message)
            await self.send_message(LOG_CHANNEL, start_message)

            # Start webserver
            app_runner = web.AppRunner(await web_server())
            await app_runner.setup()
            site = web.TCPSite(app_runner, "0.0.0.0", PORT)
            await site.start()
            logging.info(f"Web server started on 0.0.0.0:{PORT}")
            
            # --- ✅ STEP 1: Load states from DB before starting tasks ---
            logging.info("Loading AI and Autodelete states from database...")
            await load_ai_state()
            await load_autodelete_state(self.database) # Pass the db instance
            
            # --- ✅ STEP 2: Start the background greeting scheduler task from ai.py ---
            logging.info("Starting AI greeting scheduler...")
            asyncio.create_task(start_greeting_task(self))
            
        except Exception as e:
            logging.error(f"Failed to start the bot: {e}")
            try:
                await self.send_message(LOG_CHANNEL, f"Failed to start the bot: {e}")
            except Exception as send_error:
                logging.error(f"Failed to send error message to log channel: {send_error}")
            sys.exit(1)

    async def stop(self, *args):
        try:
            await self.database.close()
            await super().stop()
            logging.info("Bot Stopped 🙄")
            await self.send_message(LOG_CHANNEL, "Bot Stopped 🙄")
        except Exception as e:
            logging.error(f"Failed to stop the bot: {e}")
            try:
                await self.send_message(LOG_CHANNEL, f"Failed to stop the bot: {e}")
            except Exception as send_error:
                logging.error(f"Failed to send stop message to log channel: {send_error}")

# ------------------------------------
# 🏃 Run bot
# ------------------------------------
if __name__ == "__main__":
    bot = Bot()
    bot.run()
