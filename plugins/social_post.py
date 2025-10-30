# plugins/social_post.py
import os
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from instagrapi import Client as InstaClient
from config import ADMIN_IDS, WEBHOOK

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Instagram client setup ---
insta_client = InstaClient()
INSTA_SESSION_FILE = "sessions/insta_session.json"
os.makedirs("sessions", exist_ok=True)

DEFAULT_CAPTION = "🎬 Watch this amazing video on Instagram! #aitamilreels"  # Auto caption
DEFAULT_PHOTO_CAPTION = "📸 Beautiful moment captured! #aitamilreels"  # Auto caption for photos

def check_insta_session():
    """Check if Instagram session exists and is valid."""
    if not os.path.exists(INSTA_SESSION_FILE):
        return False
    try:
        insta_client.load_settings(INSTA_SESSION_FILE)
        user_info = insta_client.user_info(insta_client.user_id)
        logger.info(f"✅ Logged in as {user_info.username}")
        return True
    except Exception as e:
        logger.error(f"❌ Invalid Instagram session: {e}")
        return False

# --- Commands ---
@Client.on_message(filters.command("insta_login") & filters.user(ADMIN_IDS))
async def insta_login(client: Client, message: Message):
    login_url = f"{WEBHOOK}insta_login"
    await message.reply(f"🌐 Click below to log in to Instagram:\n\n{login_url}")

@Client.on_message(filters.command(["insta_post", "insta_reel", "insta_photo"]) & filters.user(ADMIN_IDS))
async def insta_post(client: Client, message: Message):
    if not check_insta_session():
        await message.reply("⚠️ Not logged in. Please run /insta_login first.")
        return

    if not message.reply_to_message:
        await message.reply("❌ Reply to a Telegram media to post.")
        return

    # Check media type
    replied_msg = message.reply_to_message
    is_video = bool(replied_msg.video)
    is_photo = bool(replied_msg.photo)
    
    if not is_video and not is_photo:
        await message.reply("❌ Reply to a photo or video to post.")
        return

    # Check command type
    command = message.command[0]
    is_reel = command == "insta_reel"
    is_photo_post = command == "insta_photo"
    
    # Validation
    if is_reel and not is_video:
        await message.reply("❌ Reels can only be created from videos. Use /insta_photo for photos.")
        return
    
    if is_photo_post and not is_photo:
        await message.reply("❌ This command is for photos only. Use /insta_post or /insta_reel for videos.")
        return
    
    # Get caption
    caption_parts = []
    for part in message.command[1:]:
        if part.startswith("--"):
            continue  # Skip flags
        caption_parts.append(part)
    
    # Set default caption based on media type
    if is_photo:
        default_caption = DEFAULT_PHOTO_CAPTION
    else:
        default_caption = DEFAULT_CAPTION
    
    caption = " ".join(caption_parts) or default_caption
    
    file_path = await replied_msg.download()
    
    # Determine post type
    if is_reel:
        post_type = "Reels"
    elif is_photo:
        post_type = "Feed (Photo)"
    else:
        post_type = "Feed (Video)"
    
    await message.reply(f"📤 Uploading to Instagram {post_type}...")

    try:
        if is_reel:
            # Upload as Reel (video only)
            insta_client.clip_upload(file_path, caption=caption)
        elif is_photo:
            # Upload as Photo
            insta_client.photo_upload(file_path, caption=caption)
        else:
            # Upload as regular Video post
            insta_client.video_upload(file_path, caption=caption)
        
        await message.reply(f"✅ Uploaded successfully to Instagram {post_type}!")
    except Exception as e:
        logger.error(f"Instagram upload failed: {e}")
        await message.reply(f"❌ Upload failed: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
