import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from config import MONGO_URI, MONGO_DB_NAME


class Database:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]
        self.ai_settings = self.db["ai_settings"]
        self.autodelete_settings = self.db["autodelete_settings"]

    # ------------------- Connection -------------------
    async def connect(self):
        await self.client.server_info()

    async def close(self):
        self.client.close()

    # ------------------- User CRUD -------------------
    async def add_user(self, user_id: int, profile: dict):
        existing = await self.users.find_one({"_id": user_id})
        if existing:
            await self.users.update_one(
                {"_id": user_id},
                {"$set": {"profile": profile}}
            )
        else:
            await self.users.insert_one({
                "_id": user_id,
                "profile": profile,
                "status": "idle",
                "partner_id": None
            })

    async def get_user(self, user_id: int):
        return await self.users.find_one({"_id": user_id})

    async def get_all_users(self):
        """Return a list of all user IDs."""
        users_cursor = self.users.find({}, {"_id": 1})
        return [doc["_id"] async for doc in users_cursor]

    async def remove_user(self, user_id: int):
        """Remove a user (used if they block the bot)."""
        await self.users.delete_one({"_id": user_id})

    async def get_total_users(self):
        """Return total number of users."""
        return await self.users.count_documents({})

    async def get_active_chats(self):
        """Return count of users with active partners."""
        return await self.users.count_documents({"partner_id": {"$ne": None}})

    # ------------------- Status -------------------
    async def update_status(self, user_id: int, status: str):
        await self.users.update_one({"_id": user_id}, {"$set": {"status": status}})

    # ------------------- Partners -------------------
    async def set_partner(self, user_id: int, partner_id: int):
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": partner_id}})

    async def reset_partner(self, user_id: int):
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": None}})

    async def reset_partners(self, user1: int, user2: int):
        await asyncio.gather(self.reset_partner(user1), self.reset_partner(user2))

    async def set_partners_atomic(self, user1: int, user2: int):
        """Set partners for two users atomically with retry."""
        max_retries = 3
        for attempt in range(max_retries):
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    try:
                        await self.users.update_one(
                            {"_id": user1},
                            {"$set": {"partner_id": user2}},
                            session=session
                        )
                        await self.users.update_one(
                            {"_id": user2},
                            {"$set": {"partner_id": user1}},
                            session=session
                        )
                        return
                    except OperationFailure as e:
                        if e.has_error_label("TransientTransactionError"):
                            print(f"DB Write Conflict (attempt {attempt + 1}/{max_retries}). Retrying...")
                            await asyncio.sleep(0.1 * (attempt + 1))
                            continue
                        else:
                            print(f"Failed to set partners atomically: {e}")
                            raise
        raise OperationFailure("Could not complete partner pairing after multiple retries.")

    # ------------------- Group Settings (AI) -------------------
    async def get_ai_status(self, chat_id: int) -> bool:
        settings = await self.ai_settings.find_one({"_id": chat_id})
        return settings.get("ai_enabled", False) if settings else False

    async def set_ai_status(self, chat_id: int, status: bool):
        await self.ai_settings.update_one(
            {"_id": chat_id},
            {"$set": {"ai_enabled": status}},
            upsert=True
        )

    async def get_all_ai_enabled_chats(self) -> set:
        cursor = self.ai_settings.find({"ai_enabled": True})
        return {doc["_id"] async for doc in cursor}

    # ------------------- Group Settings (Autodelete) -------------------
    async def get_autodelete_status(self, chat_id: int) -> bool:
        settings = await self.autodelete_settings.find_one({"_id": chat_id})
        return settings.get("autodelete_enabled", False) if settings else False

    async def set_autodelete_status(self, chat_id: int, status: bool):
        await self.autodelete_settings.update_one(
            {"_id": chat_id},
            {"$set": {"autodelete_enabled": status}},
            upsert=True
        )

    async def get_all_autodelete_enabled_chats(self) -> set:
        cursor = self.autodelete_settings.find({"autodelete_enabled": True})
        return {doc["_id"] async for doc in cursor}

    # ------------------- Group Count -------------------
    async def get_total_groups(self):
        """Return count of groups in AI settings."""
        return await self.ai_settings.count_documents({})


# ------------------- Shared instance -------------------
db = Database(MONGO_URI, MONGO_DB_NAME)
