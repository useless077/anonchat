import logging
import logging.config
import sys
import asyncio
from datetime import datetime, timezone
from pyrogram import Client
from aiohttp import web
from config import API_ID, API_HASH, BOT_TOKEN, PORT, MONGO_URI, MONGO_DB_NAME, LOG_CHANNEL
from database.users import Database
from plugins.web_support import web_server
from plugins.ai import send_greeting_message # ✅ New Import

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)


# ------------------------------------
# 📢 SCHEDULER TASK
# ------------------------------------
async def greeting_scheduler(client: Client):
    """
    Checks the time every minute and sends greetings to all AI-enabled groups.
    """
    # 💡 Note: Current time is Friday, October 3, 2025 at 3:51:30 PM IST (UTC+5:30).
    # We will use IST hours for common greeting times, converted to UTC hours.
    # Good Morning (e.g., 8:00 AM IST) -> 2:30 AM UTC
    # Good Night (e.g., 10:00 PM IST) -> 4:30 PM UTC (or 16:30 UTC)

    while True:
        # Get current time in UTC
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        current_minute = now.minute

        # Check only once at the specific minute of the hour (e.g., minute 30 for the half-hour offset)
        if current_minute == 30: 
            try:
                # Assuming get_all_ai_enabled_chats is implemented in database.users.Database
                chats = await client.database.get_all_ai_enabled_chats() 

                message_type = None
                
                # Good Morning (2 AM UTC is 7:30 AM IST; 3 AM UTC is 8:30 AM IST)
                # Checking for 2:30 AM UTC (8:00 AM IST)
                if current_hour == 2: 
                    message_type = "Good Morning"
                
                # Good Night (16 PM UTC is 9:30 PM IST; 17 PM UTC is 10:30 PM IST)
                # Checking for 16:30 UTC (10:00 PM IST)
                elif current_hour == 16: 
                    message_type = "Good Night"
                
                if message_type and chats:
                    logging.info(f"Sending {message_type} greetings to {len(chats)} chats.")
                    for chat_id in chats:
                        await send_greeting_message(client, chat_id, message_type)

            except Exception as e:
                logging.error(f"Error in greeting scheduler: {e}")

        # Wait until the next minute mark
        await asyncio.sleep(60 - now.second) 


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
        # 💡 Note: self.database is used by the scheduler
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
            
            # ✅ Start the background greeting scheduler task
            asyncio.create_task(greeting_scheduler(self)) 
            
        except Exception as e:
            logging.error(f"Failed to start the bot: {e}")
            try:
                await self.send_message(LOG_CHANNEL, f"Failed to start the bot: {e}")
            except Exception as send_error:
                logging.error(f"Failed to send error message to log channel: {send_error}")
            sys.exit(1)

    async def stop(self, *args):
        try:
            # 💡 Close all running tasks cleanly here if necessary (optional for simple bots)
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
