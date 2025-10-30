# plugins/social_post.py
import os
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from instagrapi import Client as InstaClient
from config import ADMIN_IDS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

insta_client = InstaClient()
INSTA_SESSION_FILE = "sessions/insta_session.json"
os.makedirs("sessions", exist_ok=True)


def check_insta_session():
    """Check if Instagram session exists and is valid."""
    if not os.path.exists(INSTA_SESSION_FILE):
        logger.info("No Instagram session found.")
        return False
    try:
        insta_client.load_settings(INSTA_SESSION_FILE)
        user_info = insta_client.user_info(insta_client.user_id)
        logger.info(f"✅ Logged in as {user_info.username}")
        return True
    except Exception as e:
        logger.error(f"❌ Invalid Instagram session: {e}")
        return False


@Client.on_message(filters.command("insta_login") & filters.user(ADMIN_IDS))
async def insta_login(client: Client, message: Message):
    base_url = os.getenv("WEBHOOK_URL", f"https://{client.username}.koyeb.app")
    login_url = f"{base_url}/insta_login"
    logger.info(f"Sending login URL: {login_url}")
    await message.reply(f"🌐 Click below to log in to Instagram:\n\n{login_url}")


@Client.on_message(filters.command("insta_post") & filters.user(ADMIN_IDS))
async def insta_post(client: Client, message: Message):
    logger.info(f"Received /insta_post from {message.from_user.id}")

    if not check_insta_session():
        await message.reply("⚠️ Not logged in. Please run /insta_login first.")
        return

    if not message.reply_to_message:
        await message.reply("❌ You must reply to a video message to post.")
        return

    if not message.reply_to_message.video:
        await message.reply("❌ The replied message is not a video.")
        return

    caption = " ".join(message.command[1:]) or ""
    logger.info(f"Downloading video for /insta_post command...")
    file_path = await message.reply_to_message.download()
    await message.reply("📤 Uploading video to Instagram Reels...")

    try:
        insta_client.video_upload(file_path, caption=caption, reels=True)
        await message.reply("✅ Uploaded successfully to Instagram Reels!")
        logger.info(f"Video uploaded successfully: {file_path}")
    except Exception as e:
        logger.error(f"Instagram upload failed: {e}")
        await message.reply(f"❌ Upload failed: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted temporary file: {file_path}")
