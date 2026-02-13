import asyncio
import os
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message, InputSticker
from pyrogram.errors import FloodWait

# --- CLONE STICKER PACK (REPLY METHOD) ---
@Client.on_message(filters.command("repack") & filters.reply & filters.user(ADMIN_IDS))
async def recreate_sticker_pack_reply(client: Client, message: Message):
    """
    Usage: Reply to a sticker and send:
    /repack NewPackName "New Title"
    
    Example: Reply to a sticker and send:
    /repack MyDogs "My Dog Collection"
    """
    
    # 1. Check if the reply is actually a sticker
    replied_msg = message.reply_to_message
    if not replied_msg.sticker:
        return await message.reply("❌ **Please reply to a sticker.**")

    # 2. Get the OLD Pack Name automatically from the sticker
    old_name = replied_msg.sticker.set_name
    
    if not old_name:
        return await message.reply("❌ **This sticker is not part of a pack.**")

    # 3. Get New Details from Command
    # Usage: /repack NewName "Title Here"
    if len(message.command) < 2:
        return await message.reply(
            "❌ **Usage:** `/repack NewPackName \"New Title\"`\n"
            "Example: `/repack MyDucks \"My Cool Ducks\"`",
            parse_mode="markdown"
        )

    new_name = message.command[1]
    
    # Handle title (allow spaces)
    new_title = message.command[2:] if len(message.command) > 2 else [new_name]
    new_title = " ".join(new_title).strip('"')

    status_msg = await message.reply(f"⏳ **Cloning Pack:** `{old_name}`\n➔ **New Name:** `{new_name}`")
    
    temp_dir = f"temp_repack_{old_name}"

    try:
        # 4. Fetch the OLD pack
        try:
            sticker_set = await client.get_sticker_set(old_name)
        except Exception as e:
            return await status_msg.edit(f"❌ **Error:** Could not find pack `{old_name}`.\nReason: `{e}`")

        total_stickers = len(sticker_set.stickers)
        await status_msg.edit(f"📦 Found **{total_stickers}** stickers.\n📥 **Step 1: Downloading...**")

        # 5. Download all stickers to a temp folder
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        downloaded_files = []
        
        for i, sticker in enumerate(sticker_set.stickers):
            ext = ".tgs" if sticker.is_animated else ".webp"
            filename = f"{temp_dir}/{sticker.file_unique_id}{ext}"
            
            await client.download_media(message=sticker, file_name=filename)
            downloaded_files.append(filename)
            
            if (i + 1) % 10 == 0:
                await status_msg.edit(f"📥 **Downloading...** `{i+1}/{total_stickers}`")

        # 6. Create the NEW pack with the first sticker
        await status_msg.edit(f"✅ **Download Complete.**\n🆕 **Step 2: Creating New Pack...**")
        
        user = await client.get_me()
        emoji = "✨" # Default emoji

        first_file = downloaded_files[0]
        input_sticker = InputSticker(sticker=first_file, emoji=emoji)

        try:
            await client.create_sticker_set(
                user_id=user.id,
                title=new_title,
                name=new_name,
                stickers=[input_sticker]
            )
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return await status_msg.edit(f"❌ **Failed to create pack:** `{e}`")

        # 7. Add the remaining stickers
        await status_msg.edit(f"✅ **Pack Created.**\n📤 **Step 3: Uploading remaining {total_stickers - 1} stickers...**")
        
        count = 1
        failed_count = 0
        
        for file_path in downloaded_files[1:]:
            try:
                await client.add_sticker_to_set(
                    user_id=user.id,
                    name=new_name,
                    sticker=InputSticker(sticker=file_path, emoji=emoji)
                )
                count += 1
                
                if count % 5 == 0:
                    await status_msg.edit(f"📤 **Uploading...** `{count}/{total_stickers}`")

                # --- DELAY TO AVOID SPAM ---
                await asyncio.sleep(10) 

            except FloodWait as e:
                print(f"FloodWait: {e.value}s. Waiting...")
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"Failed to add sticker {file_path}: {e}")
                failed_count += 1
                continue

        # 8. Cleanup and Finish
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        result_msg = (
            f"✅ **Pack Cloned Successfully!**\n\n"
            f"**New Name:** `{new_name}`\n"
            f"**New Title:** {new_title}\n"
            f"**Total Stickers:** {count}\n"
        )
        if failed_count > 0:
            result_msg += f"⚠️ **Failed to upload:** {failed_count}"
            
        await status_msg.edit(result_msg)

    except Exception as e:
        print(f"Error in repack: {e}")
        await status_msg.edit(f"❌ **An error occurred:** `{e}`")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
