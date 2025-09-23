from pyrogram.types import Message
from matching import add_user, remove_user, get_partner, set_partner

# Store active users
active_users = set()
sessions = {}  # user_id -> partner_id

async def handle_start(client, message: Message):
    user_id = message.from_user.id
    add_user(user_id)
    await message.reply_text(
        "👋 Welcome to AnonChat!\nYou are connected anonymously.\nStart chatting now!"
    )
    partner_id = get_partner(user_id)
    if partner_id:
        sessions[user_id] = partner_id
        sessions[partner_id] = user_id
        await client.send_message(partner_id, "✅ You are now connected to a new partner!")

async def handle_next(client, message: Message):
    user_id = message.from_user.id
    if user_id in sessions:
        old_partner = sessions.pop(user_id)
        sessions.pop(old_partner, None)
        await client.send_message(old_partner, "❌ Your partner left the chat.")
    partner_id = get_partner(user_id)
    if partner_id:
        sessions[user_id] = partner_id
        sessions[partner_id] = user_id
        await client.send_message(partner_id, "✅ You are now connected to a new partner!")
        await message.reply_text("✅ Partner switched!")
    else:
        await message.reply_text("⏳ Waiting for a new partner...")

async def handle_message(client, message: Message):
    user_id = message.from_user.id
    if user_id not in sessions:
        partner_id = get_partner(user_id)
        if partner_id:
            sessions[user_id] = partner_id
            sessions[partner_id] = user_id
        else:
            await message.reply_text("⏳ Waiting for a partner...")
            return
    partner_id = sessions[user_id]
    await client.send_message(partner_id, message.text)
