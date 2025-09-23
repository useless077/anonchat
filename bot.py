import logging
import logging.config
import sys
from pyrogram import Client, filters
from config import BOT_TOKEN, API_ID, API_HASH, PORT, MONGO_URI, MONGO_DB_NAME, LOG_CHANNEL
from aiohttp import web
from mongo.users_and_chats import Database
from plugins.web_support import web_server

# Configure logging
try:
    logging.config.fileConfig('logging.conf')
    logging.info("Logging configuration loaded successfully.")
except Exception as e:
    print(f"Error loading logging configuration: {e}")
    logging.basicConfig(level=logging.INFO)

logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)

class AnonChatBot(Client):
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

            start_message = f"{me.first_name} ✅ Bot started successfully"
            logging.info(start_message)
            await self.send_message(LOG_CHANNEL, start_message)

            # Start web server for admin if needed
            app = web.AppRunner(await web_server())
            await app.setup()
            await web.TCPSite(app, "0.0.0.0", PORT).start()
            logging.info(f"Web server started on 0.0.0.0:{PORT}")

        except Exception as e:
            logging.error(f"Failed to start the bot: {e}")
            try:
                await self.send_message(LOG_CHANNEL, f"Failed to start: {e}")
            except Exception as send_error:
                logging.error(f"Failed to send error message: {send_error}")
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
                await self.send_message(LOG_CHANNEL, f"Failed to stop: {e}")
            except Exception as send_error:
                logging.error(f"Failed to send stop message: {send_error}")

# ---- Command Handlers ----
bot = AnonChatBot()

@bot.on_message(filters.private & filters.text)
async def save_user_profile(client, message):
    """
    Example: User sends "gender:male,age:25,location:Chennai"
    """
    try:
        user_id = str(message.from_user.id)
        text = message.text.lower().replace(" ", "")
        data = {}
        for item in text.split(","):
            key, value = item.split(":")
            if key in ["gender", "age", "location"]:
                data[key] = int(value) if key == "age" else value

        # Save DP (profile photo)
        photos = await client.get_profile_photos(user_id)
        if photos.total_count > 0:
            data["dp"] = photos.photos[0].file_id

        await bot.database.add_user(user_id, data)
        await message.reply("✅ Profile saved successfully!")
        logging.info(f"User {user_id} profile saved: {data}")
    except Exception as e:
        await message.reply("❌ Failed to save profile.")
        logging.error(f"Error saving user profile: {e}")

# ---- Run bot ----
if __name__ == "__main__":
    bot.run()
