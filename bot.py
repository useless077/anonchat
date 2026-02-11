# main.py

import logging
import sys
import asyncio
from pyrogram import Client
from aiohttp import web
from config import API_ID, API_HASH, BOT_TOKEN, PORT, MONGO_URI, MONGO_DB_NAME, LOG_CHANNEL
from database.users import Database
from plugins.web_support import web_server
from utils import check_idle_chats, safe_reply

# ✅ IMPORTS FOR AUTO FORWARDER
from plugins.ai import load_ai_state, start_greeting_task
from plugins.auto_forwarder import catch_up_history, forward_worker # <--- NEW IMPORT
from utils import load_autodelete_state 

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
            
            # --- Load states ---
            logging.info("Loading AI and Autodelete states from database...")
            await load_ai_state()
            await load_autodelete_state(self.database) 
            
            # --- Start AI Greeting ---
            logging.info("Starting AI greeting scheduler...")
            asyncio.create_task(start_greeting_task(self))
            
            # --- Start Idle Chat Checker ---
            logging.info("Starting idle chat checker...")
            asyncio.create_task(check_idle_chats(lambda uid, text="⚠️ Chat closed due to inactivity.": safe_reply(bot.get_users(uid), text)))
            
            # --- ✅ NEW: Start Auto Forwarder ---
            # 1. First, check history and fill queue with old videos
           # logging.info("Starting Auto Forwarder History Check...")
           # asyncio.create_task(catch_up_history(self))

            # 2. Then, start the worker that posts videos every 15 mins
            logging.info("Starting Auto Forwarder Worker...")
            asyncio.create_task(forward_worker(self))
            # ------------------------------------
            
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
