# plugins/social_post.py

import os
import asyncio
import logging
import secrets
import random
import uuid
from typing import List

from pyrogram import Client, filters
from pyrogram.types import Message
from instagrapi import Client as InstaClient
from instagrapi.exceptions import (
    LoginRequired,
    ChallengeRequired,
    PrivateError,
    MediaNotFound,
)

from database.users import db
from config import ADMIN_IDS, WEBHOOK, MONGO_DB_NAME, INSTA_PROXIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- Instagram Client ----------------
insta_client = InstaClient()


def get_random_proxy():
    if INSTA_PROXIES:
        return random.choice(INSTA_PROXIES)
    return None


# ---------------- Session Management ----------------
async def load_insta_session() -> bool:
    logger.info(f"🔍 Checking Instagram session in DB '{MONGO_DB_NAME}'...")
    session_doc = await db.get_insta_session(MONGO_DB_NAME)

    if session_doc and "settings" in session_doc:
        try:
            proxy = get_random_proxy()
            logger.info(f"🌐 Using proxy: {proxy}")

            global insta_client
            insta_client = InstaClient(proxy=proxy)

            insta_client.set_settings(session_doc["settings"])

            # Verify session
            await asyncio.to_thread(insta_client.account_info)

            logger.info("✅ Instagram session loaded successfully.")
            return True

        except Exception as e:
            logger.error(f"❌ Invalid session: {e}")
            await db.delete_insta_session(MONGO_DB_NAME)
            return False

    logger.info("ℹ️ No Instagram session found.")
    return False


async def save_insta_session_to_db():
    try:
        settings = insta_client.get_settings()
        await db.save_insta_session(MONGO_DB_NAME, settings)
        logger.info("✅ Session saved to MongoDB.")
    except Exception as e:
        logger.error(f"❌ Failed saving session: {e}")


# ---------------- Secure Login Token ----------------
login_tokens = {}


@Client.on_message(filters.command("insta_login") & filters.user(ADMIN_IDS))
async def insta_login(client: Client, message: Message):
    token = secrets.token_urlsafe(16)
    login_tokens[token] = True

    login_url = f"{WEBHOOK}insta_login?token={token}"

    await message.reply(
        f"🌐 Login to Instagram\n\n"
        f"⚠️ Valid for 5 minutes.\n\n"
        f"[Login Here]({login_url})",
        disable_web_page_preview=True,
    )

    await asyncio.sleep(300)
    login_tokens.pop(token, None)


# ---------------- Instagram Post Command ----------------
@Client.on_message(filters.command(["insta_post", "insta_reel", "insta_photo"]) & filters.user(ADMIN_IDS))
async def insta_post(client: Client, message: Message):

    if not await load_insta_session():
        await message.reply("⚠️ Not logged in. Run `/insta_login` first.")
        return

    replied_msg = message.reply_to_message
    if not replied_msg:
        await message.reply("❌ Reply to a photo/video.")
        return

    command = message.command[0]
    is_reel = command == "insta_reel"
    is_photo_only = command == "insta_photo"

    media_group = []

    if replied_msg.media_group_id:
        try:
            media_group = await client.get_media_group(
                replied_msg.chat.id, replied_msg.id
            )
        except Exception as e:
            logger.error(e)
            await message.reply("❌ Failed to fetch media group.")
            return
    else:
        media_group = [replied_msg]

    file_paths: List[str] = []

    for msg in media_group:
        if msg.photo or msg.video:
            path = await msg.download()
            if path:
                file_paths.append(path)

    if not file_paths:
        await message.reply("❌ No valid media found.")
        return

    if is_reel and not any(msg.video for msg in media_group):
        await message.reply("❌ Reels require a video.")
        return

    if is_photo_only and any(msg.video for msg in media_group):
        await message.reply("❌ `/insta_photo` is for images only.")
        return

    caption = (
        " ".join(message.command[1:]).strip()
        or replied_msg.caption
        or "Follow for more updates 🔥"
    )

    await message.reply("📤 Uploading to Instagram...")

    try:
        # ---------------- Upload Logic ----------------
        if is_reel:
            media = await asyncio.to_thread(
                insta_client.clip_upload,
                file_paths[0],
                caption
            )

        elif len(file_paths) > 1:
            media = await asyncio.to_thread(
                insta_client.album_upload,
                file_paths,
                caption
            )

        elif file_paths[0].lower().endswith((".jpg", ".jpeg", ".png")):
            media = await asyncio.to_thread(
                insta_client.photo_upload,
                file_paths[0],
                caption
            )

        else:
            media = await asyncio.to_thread(
                insta_client.video_upload,
                file_paths[0],
                caption
            )

        # ---------------- Success ----------------
        if media and hasattr(media, "code"):
            post_url = f"https://www.instagram.com/p/{media.code}/"
            await message.reply(
                f"✅ Uploaded Successfully!\n\n🔗 {post_url}"
            )
        else:
            await message.reply("✅ Uploaded Successfully!")

    except LoginRequired:
        await message.reply("❌ Session expired. Login again.")
        await db.delete_insta_session(MONGO_DB_NAME)

    except ChallengeRequired:
        await message.reply("❌ Instagram challenge required.")

    except MediaNotFound:
        await message.reply("❌ Invalid or corrupted media.")

    except Exception as e:
        logger.error(e)
        await message.reply(f"❌ Upload failed: {e}")

    finally:
        for path in file_paths:
            if os.path.exists(path):
                os.remove(path)


# ---------------- Import Session from Chrome ----------------
@Client.on_message(filters.command("import_session") & filters.user(ADMIN_IDS))
async def import_session_cmd(client: Client, message: Message):

    if len(message.command) < 2:
        await message.reply(
            "Usage:\n`/import_session <sessionid>`"
        )
        return

    session_id = message.command[1]

    await message.reply("⏳ Verifying session...")

    try:
        temp_client = InstaClient()

        settings = {
            "cookies": {
                "sessionid": session_id
            },
            "device_settings": {
                "uuid": str(uuid.uuid4()),
                "manufacturer": "Xiaomi",
                "model": "Mi 9T",
                "android_version": 28,
                "android_release": "9.0",
            },
            "user_agent": "Instagram 219.0.0.12.117 Android",
        }

        temp_client.set_settings(settings)

        # Verify login
        temp_client.account_info()

        await db.save_insta_session(MONGO_DB_NAME, settings)

        await message.reply(
            "✅ Session Imported Successfully!\nYou can now use `/insta_post`."
        )

    except Exception as e:
        logger.error(e)
        await message.reply(f"❌ Invalid session.\nError: {e}")
