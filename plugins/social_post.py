# plugins/social_post.py
import os
import asyncio
import logging
import secrets
from typing import List, Optional

from pyrogram import Client, filters
from pyrogram.types import Message
from instagrapi import Client as InstaClient
from instagrapi.exceptions import LoginRequired, ChallengeRequired, PrivateError, MediaNotFound

# --- IMPORT YOUR SHARED DB INSTANCE ---
from database.users import db

# --- IMPORT CONFIG VALUES ---
from config import ADMIN_IDS, WEBHOOK, MONGO_DB_NAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Instagram client setup ---
insta_client = InstaClient()

# --- Session Management (using your Database class) ---
async def load_insta_session() -> bool:
    """Load Instagram session settings from MongoDB using the shared db instance."""
    logger.info(f"🔍 Checking for Instagram session in database '{MONGO_DB_NAME}'...")
    # Using MONGO_DB_NAME as the unique session identifier
    session_doc = await db.get_insta_session(MONGO_DB_NAME)
    if session_doc and "settings" in session_doc:
        try:
            insta_client.set_settings(session_doc["settings"])
            # Check if the loaded session is valid by trying to get user info
            user_info = await asyncio.to_thread(insta_client.user_info, insta_client.user_id)
            logger.info(f"✅ Logged in as {user_info.username} from MongoDB session.")
            return True
        except Exception as e:
            logger.error(f"❌ Invalid or expired session in DB: {e}")
            # Clean up the invalid session from DB
            await db.delete_insta_session(MONGO_DB_NAME)
            return False
    logger.info("ℹ️ No session found in MongoDB.")
    return False

async def save_insta_session_to_db():
    """Save current Instagram client settings to MongoDB using the shared db instance."""
    logger.info(f"💾 Saving Instagram session to database '{MONGO_DB_NAME}'...")
    try:
        settings = insta_client.get_settings()
        # Using MONGO_DB_NAME as the unique session identifier
        await db.save_insta_session(MONGO_DB_NAME, settings)
        logger.info("✅ Session saved successfully to MongoDB.")
    except Exception as e:
        logger.error(f"❌ Failed to save session to DB: {e}")

# --- In-memory token store for secure login ---
# In a real app, this should be in Redis or a DB with an expiry
login_tokens = {}

# --- Commands ---
@Client.on_message(filters.command("insta_login") & filters.user(ADMIN_IDS))
async def insta_login(client: Client, message: Message):
    """Generates a secure, one-time login link."""
    # Generate a secure token
    token = secrets.token_urlsafe(16)
    login_tokens[token] = True  # Store the token
    
    # Create the login URL with the token
    # Your web server at WEBHOOK must handle this token
    login_url = f"{WEBHOOK}insta_login?token={token}"
    
    await message.reply(
        f"🌐 Click below to log in to Instagram.\n\n"
        f"**This link is valid for a single use and expires in 5 minutes.**\n\n"
        f"[Login to Instagram]({login_url})",
        disable_web_page_preview=True
    )
    # Optional: Schedule token deletion after 5 minutes
    await asyncio.sleep(300)
    if token in login_tokens:
        del login_tokens[token]

@Client.on_message(filters.command(["insta_post", "insta_reel", "insta_photo"]) & filters.user(ADMIN_IDS))
async def insta_post(client: Client, message: Message):
    """Handles posting photos, videos, and carousels to Instagram."""
    
    # 1. Check Instagram session
    if not await load_insta_session():
        await message.reply("⚠️ Not logged in. Please run `/insta_login` first.")
        return

    # 2. Check for reply to a message
    replied_msg = message.reply_to_message
    if not replied_msg:
        await message.reply("❌ Reply to a Telegram media (photo/video) to post.")
        return

    # 3. Determine command and media type
    command = message.command[0]
    is_reel = command == "insta_reel"
    is_photo_post = command == "insta_photo"
    
    file_paths: List[str] = []
    media_group = None
    
    # 4. Handle multiple media (Carousel)
    if replied_msg.media_group_id:
        await message.reply("📦 Detected a media group. Downloading all items...")
        try:
            # Fetch all messages in the media group
            media_group = await client.get_media_group(replied_msg.chat.id, replied_msg.id)
        except Exception as e:
            logger.error(f"Failed to get media group: {e}")
            await message.reply("❌ Could not fetch all media items. Please try again.")
            return
    else:
        media_group = [replied_msg]

    # 5. Download files and validate types
    for msg in media_group:
        if msg.photo or msg.video:
            path = await msg.download()
            if path:
                file_paths.append(path)
        else:
            # Silently skip non-photo/video items in a group
            logger.warning(f"Skipping a non-photo/video item in the group: {msg.id}")

    if not file_paths:
        await message.reply("❌ No valid photos or videos found to post.")
        return

    # 6. Validate command vs media type
    if is_reel and not any(msg.video for msg in media_group):
        await message.reply("❌ Reels can only be created from videos. Use `/insta_photo` for photos.")
        return
    
    if is_photo_post and any(msg.video for msg in media_group):
        await message.reply("❌ `/insta_photo` is for photos only. Found a video. Use `/insta_post` or `/insta_reel`.")
        return

    # 7. Caption selection logic
    caption_parts = [part for part in message.command[1:] if not part.startswith("--")]
    cmd_caption = " ".join(caption_parts).strip()
    media_caption = (replied_msg.caption or "").strip()
    default_caption = "📸 𝐟𝐨𝐥𝐥𝐨𝐰 𝐟𝐨𝐫 𝐦𝐨𝐫𝐞 𝐢𝐧𝐭𝐞𝐫𝐞𝐬𝐭𝐢𝐧𝐠 𝐯𝐢𝐝𝐞𝐨𝐬. 𝐝𝐨𝐧'𝐭 𝐟𝐨𝐫𝐠𝐞𝐭 𝐭𝐨 𝐬𝐡𝐚𝐫𝐞 𝐨𝐮𝐫 𝐩𝐨𝐬𝐭.. #tamilreels #tamilaunty #tamilactresses #hotreels #trendingsong #viral" if is_photo_post else "𝐟𝐨𝐥𝐥𝐨𝐰 𝐟𝐨𝐫 𝐦𝐨𝐫𝐞 𝐢𝐧𝐭𝐞𝐫𝐞𝐬𝐭𝐢𝐧𝐠 𝐩𝐡𝐨𝐭𝐨𝐬 𝐚𝐧𝐝 𝐦𝐞𝐦𝐞𝐬. 𝐝𝐨𝐧'𝐭 𝐟𝐨𝐫𝐠𝐞𝐭 𝐭𝐨 𝐬𝐡𝐚𝐫𝐞 𝐨𝐮𝐫 𝐩𝐨𝐬𝐭.. #tamilmemes #tamilaunty #tamilactresses #trendingsong #viral"
    caption = cmd_caption or media_caption or default_caption
    
    post_type = "Reel" if is_reel else ("Carousel" if len(file_paths) > 1 else ("Photo" if file_paths[0].lower().endswith(('.jpg', '.jpeg', '.png')) else "Video"))
    await message.reply(f"📤 Uploading {len(file_paths)} item(s) to Instagram {post_type}...")

    # 8. Upload to Instagram in a separate thread to avoid blocking the bot
    try:
        media = await asyncio.to_thread(
            lambda: (
                # For Reels, only use the first video
                insta_client.clip_upload(file_paths[0], caption=caption) if is_reel
                # For Photo posts or if all files are images, use photo_upload (handles carousel)
                else insta_client.photo_upload(file_paths, caption=caption) if is_photo_post or all(p.lower().endswith(('.jpg', '.jpeg', '.png')) for p in file_paths)
                # For general video posts
                else insta_client.video_upload(file_paths, caption=caption)
            )
        )

        # 9. Handle success
        if media and hasattr(media, "code"):
            post_url = f"https://www.instagram.com/p/{media.code}/"
            await message.reply(
                f"✅ Uploaded successfully to Instagram {post_type}!\n\n📝 Caption:\n{caption}\n\n 𝗳𝗼𝗹𝗹𝗼𝘄 𝗳𝗼𝗿 𝗺𝗼𝗿𝗲 𝗶𝗻𝘁𝗲𝗿𝗲𝘀𝘁𝗶𝗻𝗴 𝘃𝗶𝗱𝗲𝗼𝘀 𝗮𝗻𝗱 𝗽𝗵𝗼𝘁𝗼𝘀😘😍💕🥵🔗 {post_url}"
            )
        else:
            await message.reply(f"✅ Uploaded successfully to Instagram {post_type}! (Link unavailable)")

    except LoginRequired:
        await message.reply("❌ Instagram session expired. Please run `/insta_login` again.")
        # Use MONGO_DB_NAME to delete the invalid session
        await db.delete_insta_session(MONGO_DB_NAME)
    except ChallengeRequired:
        await message.reply("❌ Instagram requires a challenge (e.g., verify email/code). Please log in manually via `/insta_login`.")
    except MediaNotFound:
        await message.reply("❌ Instagram could not process the media. It might be corrupted or in an unsupported format.")
    except Exception as e:
        logger.error(f"Instagram upload failed: {e}")
        await message.reply(f"❌ Upload failed: {e}")
    finally:
        # 10. Clean up downloaded files
        for path in file_paths:
            if os.path.exists(path):
                os.remove(path)
