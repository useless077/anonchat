import asyncio
import os
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from config import ADMIN_IDS

@Client.on_message(filters.command("repack") & filters.reply & filters.user(ADMIN_IDS))
async def recreate_sticker_pack_reply(client: Client, message: Message):

    replied = message.reply_to_message

    if not replied or not replied.sticker:
        return await message.reply("❌ Please reply to a sticker.")

    old_pack = replied.sticker.set_name

    if not old_pack:
        return await message.reply("❌ This sticker is not part of a pack.")

    if len(message.command) < 2:
        return await message.reply(
            "Usage:\n/repack new_pack_name \"New Title\""
        )

    new_name = message.command[1]
    new_title = " ".join(message.command[2:]).strip('"') if len(message.command) > 2 else new_name

    status = await message.reply("⏳ Fetching sticker pack...")

    # Use /tmp for compatibility
    temp_dir = f"/tmp/repack_{old_pack}"

    try:
        sticker_set = await client.get_sticker_set(old_pack)
        stickers = sticker_set.stickers

        if not stickers:
            return await status.edit("❌ No stickers found.")

        os.makedirs(temp_dir, exist_ok=True)

        await status.edit(f"📥 Downloading {len(stickers)} stickers...")

        downloaded = []

        for sticker in stickers:
            ext = ".tgs" if sticker.is_animated else ".webp"
            file_path = os.path.join(temp_dir, f"{sticker.file_unique_id}{ext}")

            await client.download_media(sticker.file_id, file_name=file_path)

            emoji = sticker.emoji or "✨"
            downloaded.append((file_path, emoji))

        me = await client.get_me()

        await status.edit("🆕 Creating new pack...")

        first_file, first_emoji = downloaded[0]

        # --- PYROGRAM V1 SYNTAX FIX ---
        # In v1, we pass the file path directly to 'stickers' 
        # and the emoji string to 'emoji'
        await client.create_sticker_set(
            user_id=me.id,
            title=new_title,
            name=new_name,
            stickers=[first_file], # List of file paths
            emoji=first_emoji      # Emoji string
        )

        await asyncio.sleep(5)  # Safe gap

        await status.edit("📤 Uploading remaining stickers...")

        count = 1

        for file_path, emoji in downloaded[1:]:
            try:
                # --- PYROGRAM V1 SYNTAX FIX ---
                await client.add_sticker_to_set(
                    user_id=me.id,
                    name=new_name,
                    sticker=file_path, # File path directly
                    emoji=emoji        # Emoji string directly
                )
                count += 1

                await asyncio.sleep(3)  # Safe delay

            except FloodWait as e:
                wait_time = e.value + 2
                await status.edit(f"⚠️ FloodWait: Sleeping {wait_time}s...")
                await asyncio.sleep(wait_time)

                # Retry after FloodWait
                await client.add_sticker_to_set(
                    user_id=me.id,
                    name=new_name,
                    sticker=file_path,
                    emoji=emoji
                )
                count += 1
                await asyncio.sleep(3)

        shutil.rmtree(temp_dir, ignore_errors=True)

        await status.edit(
            f"✅ Pack cloned successfully!\n\n"
            f"New Name: `{new_name}`\n"
            f"Title: {new_title}\n"
            f"Total Stickers: {count}"
        )

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        # Show the actual error in the log for debugging
        print(f"[REPACK ERROR] {e}")
        await status.edit(f"❌ Error: `{e}`")
