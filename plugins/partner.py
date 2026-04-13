import asyncio
import random
from datetime import datetime
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from pyrogram.errors import FloodWait, UserIsBlocked, UserIsBot
import config
from utils import (    
    add_user,
    remove_user,
    set_partner,
    update_activity,
    sessions,
    start_profile_timer,
    log_message,
    check_partner_wait,
    send_search_progress,
    cancel_search,
    waiting_users, 
    schedule_deletion,
    AUTO_DELETE_DELAY
)
from database.users import db

# --- GLOBAL STATE FOR ANONYMOUS CHAT ---
profile_states = {}
profile_data = {}
profile_timeouts = {}
connection_messages = {} 
waiting_lock = asyncio.Lock()
search_flood = {} 

REACTION_EMOJIS = ["👍", "👌", "❤️", "🥰", "😊", "✅", "👏", "😍"]
CONNECTION_STICKER_ID = "CAACAgUAAyEFAASH239qAAPmaNu1X46I2IKBOBtfNH3ot9jO0MsAAmIaAAKEFOBWbLL49T60Z7QeBA"

# ----------------- Profile -----------------
@Client.on_message(filters.private & filters.command("profile"))
async def profile_cmd(client, message):
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if user and user.get("profile", {}).get("name"):
        await message.reply_text(
            "✅ **You have already set the profile.**\n\n"
            "Use **bot settings** to update the details."
        )
        return

    profile_states[user_id] = "name"
    profile_data[user_id] = {}

    async def send_timeout(msg):
        await client.send_message(user_id, msg)

    await start_profile_timer(user_id, send_timeout)
    await message.reply_text("✏️ **sᴇɴᴅ ʏᴏᴜʀ ꜰᴜʟʟ ɴᴀᴍᴇ:**")
    
@Client.on_callback_query(filters.regex("^gender_"))
async def gender_cb(client, query):
    user_id = query.from_user.id
    gender = query.data.split("_")[1]
    profile_data[user_id]["gender"] = gender
    profile_states[user_id] = "age"
    await query.answer(f"✅ Gender '{gender}' selected")
    await query.message.reply_text("**ɴᴏᴡ ꜱᴇɴᴅ ʏᴏᴜʀ ᴀɢᴇ (10-99):**")

# FIXED: Changed to group=1
@Client.on_message(filters.private, group=1) 
async def profile_steps(client, message):
    user_id = message.from_user.id
    
    if user_id not in profile_states: 
        return
    
    if message.text and message.text.startswith('/'):
        return
    
    profile_timeouts[user_id] = datetime.utcnow()
    step = profile_states[user_id]
    
    if not message.text and step in ["name", "age", "location"]:
        await message.reply_text("❌ **ᴘʟᴇᴀꜱᴇ ꜱᴇɴᴅ ᴏɴʟʏ ᴛᴇxᴛ ɪɴᴍᴜᴜᴛ ꜰᴏʀ ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ ᴅᴇᴛᴀɪʟꜱ (ɴᴀᴍᴇ, ᴀɢᴇ, ʟᴏᴄᴀᴛɪᴏɴ).**")
        return

    text = message.text.strip()
    
    if step == "name":
        profile_data[user_id]["name"] = text
        profile_states[user_id] = "gender"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Male", callback_data="gender_male")],
            [InlineKeyboardButton("Female", callback_data="gender_female")],
            [InlineKeyboardButton("Shemale", callback_data="gender_shemale")]
        ])
        await message.reply_text("✅ **ɴᴀᴍᴇ ꜱᴀᴠᴇᴅ. ᴄʜᴏᴏꜱᴇ ɢᴇɴᴅᴇʀ:**", reply_markup=buttons)
    
    elif step == "age":
        if not text.isdigit() or not (10 <= int(text) <= 99):
            await message.reply_text("❌ **ᴇɴᴛᴇʀ ᴠᴀʟɪᴅ ᴀɢᴇ (10-99)**")
            return
        profile_data[user_id]["age"] = int(text)
        profile_states[user_id] = "location"
        await message.reply_text("✅ **ᴀɢᴇ ꜱᴀᴠᴇᴅ. ɴᴏᴡ ꜱᴇɴᴅ ʏᴏᴜʀ ʟᴏᴄᴀᴛɪᴏɴ (ᴄɪᴛʏ/ᴄᴏᴜɴᴛʀʏ):**")
    
    elif step == "location":
        profile_data[user_id]["location"] = text
        user = await db.get_user(user_id)
        profile = user.get("profile", {}) if user else {}
        profile.update(profile_data[user_id])
        
        await db.add_user(user_id, profile, user_type="user")
        
        profile_states.pop(user_id, None)
        profile_data.pop(user_id, None)
        profile_timeouts.pop(user_id, None)
        
        await message.reply_text("🎉 **ᴘʀᴏꜰɪʟᴇ ᴜᴘᴅᴀᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜰꜟʟʏ!**")
    
    return

@Client.on_message(filters.private & filters.command("myprofile"))
async def myprofile_cmd(client, message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    profile = user.get("profile", {}) if user else {}
    if not profile or not profile.get("gender"):
        await message.reply_text("⚠️ **ʏᴏᴜ ʜᴀᴠᴇ ɴᴏᴛ ꜱᴇᴛ ᴘʀᴏꜰɪʟᴇ ʏᴇᴛ. ᴜꜱᴇ /ᴘʀᴏꜰɪʟᴇ**")
        return
    caption = "👤 **ʏᴏᴜʀ ᴘʀᴏꜰɪʟᴇ**\n\n"
    caption += f"• **ɴᴀᴍᴇ:** {profile.get('name','')}\n"
    caption += f"• **ɢᴇɴᴅᴇʀ:** {profile.get('gender','')}\n"
    caption += f"• **ᴀɢᴇ:** {profile.get('age','')}\n"
    caption += f"• **ʟᴏᴄᴀᴛɪᴏɴ:** {profile.get('location','')}\n"
    await message.reply_text(caption, parse_mode=enums.ParseMode.HTML)

@Client.on_message(filters.private & filters.command("cancel"))
async def cancel_search_cmd(client, message):
    """Allow users to cancel their partner search."""
    user_id = message.from_user.id
    
    if await cancel_search(user_id):
        await message.reply_text("❌ **ꜱᴇᴀʀᴄʜ ᴄᴀɴᴄᴇʟʟᴇᴅ.**")
    else:
        await message.reply_text("⚠️ **ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ꜱᴇᴀʀᴄʜɪɴɢ ꜰᴏʀ ᴀ ᴘᴀʀᴛɴᴇʀ ʀɪɢʜᴛ ɴᴏᴡ.**")

# ----------------- Search Partner -----------------
@Client.on_message(filters.command("search"))
async def search_command(client: Client, message: Message):
    user_id = message.from_user.id

    if message.from_user.is_bot:
        if len(message.command) > 1:
            user_id = int(message.command[1])
        else:
            return

    if user_id in search_flood and (datetime.utcnow() - search_flood[user_id]).total_seconds() < 3:
        return

    search_flood[user_id] = datetime.utcnow()
    
    async with waiting_lock:
        if user_id in sessions:
            await message.reply_text("**ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴀ ᴄʜᴀᴛ. ᴜꜱᴇ /ᴇɴᴅ ᴛᴏ ʟᴇᴀᴠᴇ ꜰɪʀꜱᴛ.**")
            return
        if user_id in waiting_users:
            await message.reply_text("**ʏᴏᴜ ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ꜱᴇᴀʀᴄʜɪɴɢ ꜰᴏʀ ᴀ ᴘᴀʀᴛɴᴇʀ... ᴘʟᴇᴀꜱᴇ ᴡᴇᴀɪᴛ.**")
            return

        waiting_users.add(user_id)
        search_msg = await message.reply_text("🔍 **ꜱᴇᴀʀᴄʜɪɴɢ ꜰᴏʀ ᴀ ᴘᴀʀᴛɴᴇʀ...**")

        asyncio.create_task(check_partner_wait(client, user_id, search_msg))
        asyncio.create_task(send_search_progress(client, user_id, search_msg))

        if len(waiting_users) > 1:
            user1_id = waiting_users.pop()
            user2_id = waiting_users.pop()

            try:
                try:
                    await search_msg.delete()
                except Exception:
                    pass

                set_partner(user1_id, user2_id)
                await db.set_partners_atomic(user1_id, user2_id)
                await db.update_status(user1_id, "chatting")
                await db.update_status(user2_id, "chatting")

                user_objects = await client.get_users([user1_id, user2_id])
                user1_obj, user2_obj = user_objects[0], user_objects[1]

                await client.send_sticker(user1_id, CONNECTION_STICKER_ID)
                await client.send_sticker(user2_id, CONNECTION_STICKER_ID)
                await asyncio.sleep(0.5)

                emojis = random.sample(REACTION_EMOJIS, 3)
                emoji_string = " ".join(emojis)

                user1_db = await db.get_user(user1_id)
                user2_db = await db.get_user(user2_id)
                profile1 = user1_db.get("profile", {})
                profile2 = user2_db.get("profile", {})

                partner2_name = profile2.get("name", "Not found")
                partner2_age = profile2.get("age", "Not found")
                partner2_gender = profile2.get("gender", "Not found")
                
                buttons_user1 = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭️ ɴᴇᴋᴛ", callback_data="menu_next"), InlineKeyboardButton("🔌 ᴇɴᴅ", callback_data="menu_end")]
                ])

                text_for_user1 = (
                    f"{emoji_string}\n\n"
                    "🎉 **ᴄᴏɴɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! ʏᴏᴜ ᴀʀᴇ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴡɪᴛʜ ᴀ ᴘᴀʀᴛɴᴇʀ.**\n\n"
                    "👤 **ᴘᴀʀᴛɴᴇʀ'ꜱ ᴅᴇᴛᴀɪʟꜱ:**\n"
                    f"• **ɴᴀᴍᴇ:** {partner2_name}\n"
                    f"• **ᴀɢᴇ:** {partner2_age}\n"
                    f"• **ɢᴇɴᴅᴇʀ:** {partner2_gender}\n\n"
                    "**ꜱᴀʏ ʜɪ ᴛᴏ ꜱᴛᴀʀᴛ ᴛʜᴇ ᴄᴏɴᴠᴇʀꜱᴀᴛɪᴏɴ!**"
                )
                
                partner1_name = profile1.get("name", "Not found")
                partner1_age = profile1.get("age", "Not found")
                partner1_gender = profile1.get("gender", "Not found")
                
                buttons_user2 = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭️ ɴᴇᴋᴛ", callback_data="menu_next"), InlineKeyboardButton("🔌 ᴇɴᴅ", callback_data="menu_end")]
                ])

                text_for_user2 = (
                    f"{emoji_string}\n\n"
                    "🎉 **ᴄᴏɴɢʀᴀᴛᴜʟᴀᴛɪᴏɴꜱ! ʏᴏᴜ ᴀʀᴇ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴡɪᴛʜ ᴀ ᴘᴀʀᴛɴᴇʀ.**\n\n"
                    "👤 **ᴘᴀʀᴛɴᴇʀ'ꜱ ᴅᴇᴛᴀɪʟꜱ:**\n"
                    f"• **ɴᴀᴍᴇ:** {partner1_name}\n"
                    f"• **ᴀɢᴇ:** {partner1_age}\n"
                    f"• **ɢᴇɴᴅᴇʀ:** {partner1_gender}\n\n"
                    "**ꜱᴀʏ ʜɪ ᴛᴏ ꜱᴛᴀʀᴛ ᴛʜᴇ ᴄᴏɴᴠᴇʀꜱᴀᴛɪᴏɴ!**"
                )

                msg1 = await client.send_message(user1_id, text_for_user1, reply_markup=buttons_user1, parse_mode=enums.ParseMode.HTML)
                msg2 = await client.send_message(user2_id, text_for_user2, reply_markup=buttons_user2, parse_mode=enums.ParseMode.HTML)

                connection_messages[user1_id] = msg1.id
                connection_messages[user2_id] = msg2.id

                print(f"[SEARCH] Successfully paired {user1_id} with {user2_id}")

                def format_user_info(user):
                    username = f"@{user.username}" if user.username else "No Username"
                    return f"<a href='tg://user?id={user.id}'>{user.first_name}</a> ({username}) `[ID: {user.id}]`"

                log_text = (
                    f"🤝 **New Pairing**\n\n"
                    f"👤 **User 1:** {format_user_info(user1_obj)}\n"
                    f"👤 **User 2:** {format_user_info(user2_obj)}"
                )

                async def log_pairing():
                    try:
                        await client.send_message(config.LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)
                    except Exception as e:
                        print(f"[SEARCH] Failed to log pairing: {e}")
                
                client.loop.create_task(log_pairing())

            except UserIsBlocked:
                sessions.pop(user1_id, None)
                sessions.pop(user2_id, None)
                await db.reset_partners(user1_id, user2_id)
                await db.update_status(user1_id, "idle")
                await db.update_status(user2_id, "idle")

            except UserIsBot:
                sessions.pop(user1_id, None)
                sessions.pop(user2_id, None)
                await db.reset_partners(user1_id, user2_id)

            except FloodWait as e:
                await asyncio.sleep(e.value)

            except Exception as e:
                print(f"[SEARCH] Error during pairing {user1_id} and {user2_id}: {e}")
                sessions.pop(user1_id, None)
                sessions.pop(user2_id, None)
                await db.reset_partners(user1_id, user2_id)
                try:
                    await client.send_message(user1_id, "❌ **ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜᴍʀᴇᴅ. ᴘʟᴇᴀꜱᴇ ᴛʀʏ ꜱᴇᴀʀᴄʜɪɴɢ ᴀɢᴀɪɴ.**")
                except Exception: pass
                try:
                    await client.send_message(user2_id, "❌ **ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜᴍʀᴇᴅ. ᴘʟᴇᴀꜱᴇ ᴛʀʏ ꜱᴇᴀʀᴄʰɪɴɢ ᴀɢᴀɪɴ.**")
                except Exception: pass

# ----------------- Callbacks for Connection Buttons -----------------
@Client.on_callback_query(filters.regex("^menu_next$"))
async def menu_next_cb(client, query):
    user_id = query.from_user.id 
    partner_id = sessions.pop(user_id, None)

    if partner_id:
        sessions.pop(partner_id, None)
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")
        waiting_users.discard(user_id)
        waiting_users.discard(partner_id)
        remove_user(user_id)
        remove_user(partner_id)

        if user_id in connection_messages:
            try:
                await client.delete_messages(user_id, [connection_messages[user_id]])
                connection_messages.pop(user_id, None)
            except Exception:
                pass
        
        await client.send_message(user_id, "🔄 **Searching for next partner...**")
        await client.send_message(partner_id, "❌ **Your partner has left the chat. Use /search to find a new partner**")

        async with waiting_lock:
            if user_id not in sessions and user_id not in waiting_users:
                waiting_users.add(user_id)
                search_msg = await client.send_message(user_id, "🔍 **Searching for a partner...**")
                asyncio.create_task(check_partner_wait(client, user_id, search_msg))
                asyncio.create_task(send_search_progress(client, user_id, search_msg))

                if len(waiting_users) > 1:
                    user1_id = waiting_users.pop()
                    user2_id = waiting_users.pop()
                    
                    if user1_id == user2_id:
                         waiting_users.add(user1_id)
                         return

                    try:
                        await search_msg.delete()
                    except Exception:
                        pass

                    set_partner(user1_id, user2_id)
                    await db.set_partners_atomic(user1_id, user2_id)
                    await db.update_status(user1_id, "chatting")
                    await db.update_status(user2_id, "chatting")
        
    else:
        await query.answer("You are not chatting with anyone.")
        await client.send_message(user_id, "⚠️ **You are not in a chat. Starting new search...**")
        await search_command(client, await client.get_messages(user_id, 0)) 


@Client.on_callback_query(filters.regex("^menu_end$"))
async def menu_end_cb(client, query):
    user_id = query.from_user.id
    
    partner_id = sessions.get(user_id)
    if not partner_id:
        user = await db.get_user(user_id)
        partner_id = user.get("partner_id") if user else None
    
    if partner_id:
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")
        sessions.pop(user_id, None)
        sessions.pop(partner_id, None)
        waiting_users.discard(user_id)
        waiting_users.discard(partner_id)

        if user_id in connection_messages:
            try:
                await client.delete_messages(user_id, [connection_messages[user_id]])
                connection_messages.pop(user_id, None)
            except Exception:
                pass
        
        if partner_id in connection_messages:
            try:
                await client.delete_messages(partner_id, [connection_messages[partner_id]])
                connection_messages.pop(partner_id, None)
            except Exception:
                pass

        await client.send_message(user_id, "❌ **You disconnected from the chat. Use /search to find new partner.**")
        
        try:
            await client.send_message(partner_id, "❌ **Your partner has disconnected. Use /search to find new partner.**")
        except UserIsBlocked:
            print(f"[menu_end] Could not notify {partner_id}")
        except Exception as e:
            print(f"[menu_end] Could not notify partner {partner_id}: {e}")
            
    else:
        await query.answer("You are not connected to anyone.")
        await client.send_message(user_id, "⚠️ **You are not connected to anyone.**")
        
# ----------------- Next / End -----------------
@Client.on_message(filters.private & filters.command("next"))
async def next_cmd(client, message):
    user_id = message.from_user.id
    partner_id = sessions.pop(user_id, None)
    if partner_id:
        if user_id in connection_messages:
            try:
                await client.delete_messages(user_id, [connection_messages[user_id]])
                connection_messages.pop(user_id, None)
            except Exception:
                pass
        
        if partner_id in connection_messages:
            try:
                await client.delete_messages(partner_id, [connection_messages[partner_id]])
                connection_messages.pop(partner_id, None)
            except Exception:
                pass

        sessions.pop(partner_id, None)
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")
        waiting_users.discard(user_id)
        waiting_users.discard(partner_id)
        remove_user(user_id)
        remove_user(partner_id)

        try:
            user_objects = await client.get_users([user_id, partner_id])
            user_obj, partner_obj = user_objects[0], user_objects[1]
            
            def format_user_info(user):
                username = f"@{user.username}" if user.username else "No Username"
                return f"<a href='tg://user?id={user.id}'>{user.first_name}</a> ({username}) `[ID: {user.id}]`"

            log_text = (
                f"⏭️ **ᴘᴀʀᴛɴᴇʀ ꜱᴋɪᴘᴘᴘᴇᴅ**\n\n"
                f"👤 **ᴜꜱᴇʀ:** {format_user_info(user_obj)}\n"
                f"👤 **ꜱᴋᴇᴘᴘᴘᴇᴅ ᴘᴀʀᴛɴɴᴇʀ:** {format_user_info(partner_obj)}"
            )
            
            async def log_skip():
                try:
                    await client.send_message(config.LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)
                except Exception as e:
                    print(f"[NEXT_CMD] Failed to log skip: {e}")
            
            client.loop.create_task(log_skip())
        except Exception as e:
            print(f"[NEXT_CMD] Could not fetch user info for logging: {e}")

        await client.send_message(user_id, "🔄 **ꜱᴇᴀʀᴄʜɪɴɴɢ ꜰᴏʀ ɴᴇxᴛ ᴍᴀʀᴛɴᴇʀ...**")
        await client.send_message(partner_id, "❌ **ʏᴏᴜʀ ᴘᴀʀᴛɴᴇʀ ʟᴇꜰᴛ.**")
        
        await search_command(client, message)
    else:
        await search_command(client, message)



@Client.on_message(filters.private & filters.command("end"))
async def end_chat(client: Client, message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    partner_id = sessions.get(user_id)
    if not partner_id:
        user = await db.get_user(user_id)
        partner_id = user.get("partner_id") if user else None

    if partner_id:
        if user_id in connection_messages:
            try:
                await client.delete_messages(user_id, [connection_messages[user_id]])
                connection_messages.pop(user_id, None)
            except Exception: pass
            
        if partner_id in connection_messages:
            try:
                await client.delete_messages(partner_id, [connection_messages[partner_id]])
                connection_messages.pop(partner_id, None)
            except Exception: pass

        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")
        sessions.pop(user_id, None)
        sessions.pop(partner_id, None)
        waiting_users.discard(user_id)
        waiting_users.discard(partner_id)

        try:
            user_objects = await client.get_users([user_id, partner_id])
            user_obj, partner_obj = user_objects[0], user_objects[1]

            def format_user_info(user):
                username = f"@{user.username}" if user.username else "No Username"
                return f"<a href='tg://user?id={user.id}'>{user.first_name}</a> ({username}) `[ID: {user_id}]`"

            log_text = (
                f"🔌 **ᴄʜᴀᴛ ᴇɴᴅᴇᴅ**\n\n"
                f"👤 **ᴜꜱᴇʀ:** {format_user_info(user_obj)}\n"
                f"👤 **ᴡɪᴛʜ ᴍᴀʀᴛɴᴇʀ:** {format_user_info(partner_obj)}"
            )

            async def log_end():
                try:
                    await client.send_message(config.LOG_CHANNEL, log_text, parse_mode=enums.ParseMode.HTML)
                except Exception as e:
                    print(f"[END_CHAT] Failed to log end: {e}")

            client.loop.create_task(log_end())
        except Exception as e:
            print(f"[END_CHAT] Could not fetch user info for logging: {e}")

        await client.send_message(user_id, "❌ **ʏᴏᴜ ᴅɪꜱᴄᴏɴɴᴇᴄᴛᴇᴅ ꜰʀᴏᴍ ᴛʜᴇ ᴄʜᴀᴛ.**")
        
        try:
            await client.send_message(partner_id, "❌ **ʏᴏᴜʀ ᴍᴀʀᴛɴᴇʀ ᴅɪꜱᴄᴏɴɴᴇᴇᴅ.**")
        except UserIsBlocked:
            print(f"[end_chat] Could not notify {partner_id}")
        except Exception as e:
            print(f"[end_chat] Could not notify partner {partner_id}: {e}")
            
    else:
        waiting_users.discard(user_id)
        sessions.pop(user_id, None)
        await db.update_status(user_id, "idle")
        await message.reply_text("⚠️ **ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴛᴏ ᴀɴʏᴏɴᴇ.**")

# ----------------- Relay Messages & Media -----------------

# CRITICAL FIX: Changed to group=0 so it runs FIRST before anything else
@Client.on_message(filters.private, group=2)
async def relay_all(client: Client, message: Message):
    user_id = message.from_user.id
    
    if message.text and message.text.startswith('/'):
        return
        
    if user_id in profile_states:
        return

    partner_id = sessions.get(user_id)
    if not partner_id:
        user_db = await db.get_user(user_id)
        partner_id = user_db.get("partner_id") if user_db else None
        if partner_id:
            partner_user = await db.get_user(partner_id)
            if partner_user and partner_user.get("partner_id") == user_id:
                sessions[user_id] = partner_id
                sessions[partner_id] = user_id
            else:
                await db.reset_partner(user_id)
                partner_id = None
    
    if not partner_id:
        return # Don't send error here, let it fall through to other handlers

    try:
        relayed_message = await message.copy(chat_id=partner_id)
        
        if not message.text:
            print(f"[AUTODELETE] Scheduling deletion of private media message {message.id}")
            await schedule_deletion(client, message.chat.id, [message.id], delay=AUTO_DELETE_DELAY)
            print(f"[AUTODELETE] Scheduling deletion of relayed message {relayed_message.id}")
            await schedule_deletion(client, partner_id, [relayed_message.id], delay=AUTO_DELETE_DELAY)
        
        async def add_reaction():
            try:
                random_emoji = random.choice(REACTION_EMOJIS)         
                await message.react(random_emoji)
            except Exception:
                pass
        client.loop.create_task(add_reaction())
        update_activity(user_id)
        update_activity(partner_id)

    except FloodWait as e:
        print(f"[relay_all] FloodWait: {e.value}s. Waiting...")
        await asyncio.sleep(e.value)
        await message.copy(chat_id=partner_id)

    except UserIsBlocked:
        print(f"[relay_all] User {partner_id} has blocked the bot. Ending chat.")
        await client.send_message(user_id, "❌ **ʏᴏᴜʀ ᴍᴀʀᴛɴᴇʀ ᴅɪꜱᴄᴏɴɴᴇᴄᴇᴅ.**")
        sessions.pop(user_id, None)
        sessions.pop(partner_id, None)
        await db.reset_partners(user_id, partner_id)
        await db.update_status(user_id, "idle")
        await db.update_status(partner_id, "idle")

    except Exception as e:
        print(f"[relay_all] Relay failed for {user_id}: {e}")
        await client.send_message(user_id, "❌ **ᴍᴇꜱꜱᴀɢᴇ ꜰᴀɪʟᴇᴅ. ᴄᴏɴɴᴇᴄᴛɪᴏɴ ᴇɴᴅ. ᴜꜱ /search ᴛᴏ ꜰɪɴᴅ ᴀ ɴᴡ ᴍᴀʀᴛɴᴇʀ.**")
        sessions.pop(user_id, None)
        await db.update_status(user_id, "idle")
        if partner_id:
            await client.send_message(partner_id, "❌ **ᴄᴏɴɴᴇᴄᴛɪᴏɴ ʟᴏꜱᴛ ᴅᴜᴇ ᴛᴏ ᴀɴ ᴇʀʀᴏʀ. ᴜꜱ /search ᴛᴏ ꜰɪɴᴅ ᴀ ɴᴡ ᴍᴀʀᴛɴᴇʀ.**")
            sessions.pop(partner_id, None)
            await db.reset_partners(user_id, partner_id)
            await db.update_status(partner_id, "idle")
        return

    try:
        client.loop.create_task(log_message(client, user_id, message.from_user.first_name, message))
    except Exception as e:
        print(f"[relay_all] Logging failed: {e}")
