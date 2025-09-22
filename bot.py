from pyrogram import Client, filters

def register_handlers(pyro: Client):
    @pyro.on_message(filters.private & ~filters.command("start"))
    async def chat_handler(client, message):
        await message.reply("Hello from bot!")
