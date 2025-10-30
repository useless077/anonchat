# bot.py
import logging
import sys
import asyncio
from pyrogram import Client
from aiohttp import web
from config import API_ID, API_HASH, BOT_TOKEN, PORT, MONGO_URI, MONGO_DB_NAME, LOG_CHANNEL
from database.users import Database
from plugins.web_support import web_server
from utils import check_idle_chats, safe_reply
from plugins.ai import load_ai_state, start_greeting_task
from utils import load_autodelete_state

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="AnonChatBot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
        )
        self.database = Database(MONGO_URI, MONGO_DB_NAME)

    async def start(self):
        try:
            await self.database.connect()
            await super().start()
            me = await self.get_me()
            self.mention = me.mention
            self.username = me.username

            start_message = f"{me.first_name} ✅ BOT started successfully ✅"
            logging.info(start_message)
            await self.send_message(LOG_CHANNEL, start_message)

            # Load AI and autodelete states
            await load_ai_state()
            await load_autodelete_state(self.database)

            # Start background tasks
            asyncio.create_task(start_greeting_task(self))
            asyncio.create_task(
                check_idle_chats(lambda uid, text="⚠️ Chat closed due to inactivity.": safe_reply(self.get_users(uid), text))
            )

            # Start aiohttp server for /insta_login page
            web_app = await web_server()
            runner = web.AppRunner(web_app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", PORT)
            await site.start()
            logging.info(f"Web server running on port {PORT}")

        except Exception as e:
            logging.error(f"Failed to start bot: {e}")
            try:
                await self.send_message(LOG_CHANNEL, f"Failed to start bot: {e}")
            except:
                pass
            sys.exit(1)

    async def stop(self, *args):
        try:
            await self.database.close()
            await super().stop()
            logging.info("Bot Stopped 🙄")
            await self.send_message(LOG_CHANNEL, "Bot Stopped 🙄")
        except Exception as e:
            logging.error(f"Failed to stop bot: {e}")
            try:
                await self.send_message(LOG_CHANNEL, f"Failed to stop bot: {e}")
            except:
                pass

if __name__ == "__main__":
    bot = Bot()
    bot.run()  # ✅ Uses long-polling; no webhooks
