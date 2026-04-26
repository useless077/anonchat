import asyncio
import os
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import ADMIN_IDS

@Client.on_message(filters.command("repack") & filters.reply & filters.user(ADMIN_IDS))
async def recreate_sticker_pack_reply(client: Client, message: Message):

    # Get the replied sticker
    replied = message.reply_to_message

    if not replied or not replied.sticker:
        return await message.reply("❌ Please reply to a sticker.")

    # 1. Get the OLD Pack Name
    old_pack = replied.sticker.set_name

    if not old_pack:
        return await message.reply("❌ This sticker is not part of a pack.")

    # 2. Get New Details from Command
    if len(message.command) < 2:
        return await message.reply(
            "Usage:\n/repack new_pack_name \"New Title\""
        )

    new_name = message.command[1]
    new_title = " ".join(message.command[2:]).strip('"') if len(message.command) > 2 else new_name

    status = await message.reply("⏳ Fetching sticker pack info...")
    
    # Use /tmp for compatibility
    temp_dir = f"/tmp/repack_{old_pack}"

    try:
        # 3. Iterate history to get ALL stickers (Version Agnostic Fix)
        # We limit to 120 to ensure speed and reliability.
        # This works on Pyrogram v1, v2, and Pyrofork.
        sticker_files = []
        
        async for msg in client.get_chat_history(old_pack, limit=120):
            if msg.sticker:
                # Download sticker to temp dir
                ext = ".tgs" if msg.sticker.is_animated else ".webp"
                file_path = os.path.join(temp_dir, f"{msg.sticker.file_unique_id}{ext}")
                
                await client.download_media(msg.file_id, file_name=file_path)
                
                # Get emoji, fallback to sparkle if missing
                emoji = msg.sticker.emoji or "✨"
                sticker_files.append((file_path, emoji))

        if not sticker_files:
            return await status.edit("❌ No stickers found in the first 120 messages.")

        # 4. Create New Pack (First Sticker)
        me = await client.get_me()
        first_file, first_emoji = sticker_files[0]

        status = await status.edit("🆕 Creating new pack...")

        # Standard syntax compatible with both v1 and v2
        await client.create_sticker_set(
            user_id=me.id, 
            title=new_title, 
            name=new_name, 
            stickers=[first_file],
            emoji=first_emoji
        )

        await asyncio.sleep(5)  # Safe gap

        # 5. Upload Remaining Stickers
        count = 1
        status = await status.edit("📤 Uploading remaining stickers...")

        for file_path, emoji in sticker_files[1:]:
            try:
                await client.add_sticker_to_set(
                    user_id=me.id,
                    name=new_name,
                    sticker=file_path,
                    emoji=emoji
                )
                count += 1
                
                # Update progress every 5 stickers
                if count % 5 == 0:
                    await status.edit(f"📤 Uploading... `{count}`")

                await asyncio.sleep(2)  # Short delay to prevent FloodWait

            except FloodWait as e:
                # Handle rate limiting gracefully
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

        # 6. Cleanup and Finish
        shutil.rmtree(temp_dir, ignore_errors=True)

        await status.edit(
            f"✅ **Pack Cloned Successfully!**\n\n"
            f"New Name: `{new_name}`\n"
            f"Title: {new_title}\n"
            f"Total Stickers: `{count}`"
        )

    except Exception as e:
        # Cleanup on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[REPACK ERROR] {e}")
        await status.edit(f"❌ **Error:** `{e}`")
