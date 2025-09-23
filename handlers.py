from pyrogram.types import Message
from matching import add_user, get_partner

# Store active users
active_users = set()

async def handle_start(client, message: Message):
    user_id = message.from_user.id
    add_user(user_id)
    await message.reply_text("👋 Welcome to AnonChat!\nYou are connected anonymously.\nStart chatting now!")

async def handle_message(client, message: Message):
    user_id = message.from_user.id
    add_user(user_id)
    
    partner_id = get_partner(user_id)
    if partner_id:
        await client.send_message(partner_id, message.text)
        await message.reply_text("Message sent to your chat partner!")
    else:
        await message.reply_text("Waiting for a chat partner...")
