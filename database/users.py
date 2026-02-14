# database/users.py

import asyncio
from typing import Optional, Dict, Any, List, Set
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from config import MONGO_URI, MONGO_DB_NAME


class Database:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]

        # Collections
        self.users = self.db["users"]
        self.groups = self.db["groups"]
        self.ai_settings = self.db["ai_settings"]
        self.autodelete_settings = self.db["autodelete_settings"]
        self.insta_sessions = self.db["insta_sessions"]
        self.forwarder_checkpoint = self.db["forwarder_checkpoints"]

    # ------------------- Connection -------------------

    async def connect(self):
        await self.client.server_info()

    async def close(self):
        self.client.close()

    # ===================== USERS ======================

    async def add_user(self, user_id: int, profile: Optional[dict] = None, user_type: str = "user"):
        existing = await self.users.find_one({"_id": user_id})

        if existing:
            update_fields = {}
            if profile is not None:
                update_fields["profile"] = profile
            if user_type is not None:
                update_fields["user_type"] = user_type

            if update_fields:
                await self.users.update_one({"_id": user_id}, {"$set": update_fields})
        else:
            await self.users.insert_one({
                "_id": user_id,
                "profile": profile or {},
                "status": "idle",
                "partner_id": None,
                "user_type": user_type
            })

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        return await self.users.find_one({"_id": user_id})

    async def get_all_users(self) -> List[int]:
        cursor = self.users.find({}, {"_id": 1})
        return [doc["_id"] async for doc in cursor]

    async def remove_user(self, user_id: int):
        await self.users.delete_one({"_id": user_id})

    async def get_total_users(self) -> int:
        return await self.users.count_documents({})

    # ===================== STATUS ======================

    async def update_status(self, user_id: int, status: str):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"status": status}},
            upsert=True
        )

    # ===================== PARTNERS ======================

    async def set_partner(self, user_id: int, partner_id: int):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"partner_id": partner_id}},
            upsert=True
        )

    async def reset_partner(self, user_id: int):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"partner_id": None}}
        )

    async def reset_partners(self, user1: int, user2: int):
        await asyncio.gather(
            self.reset_partner(user1),
            self.reset_partner(user2)
        )

    async def set_partners_atomic(self, user1: int, user2: int):
        max_retries = 3

        for attempt in range(max_retries):
            async with await self.client.start_session() as session:
                async with session.start_transaction():
                    try:
                        await self.users.update_one(
                            {"_id": user1},
                            {"$set": {"partner_id": user2}},
                            session=session,
                            upsert=True
                        )
                        await self.users.update_one(
                            {"_id": user2},
                            {"$set": {"partner_id": user1}},
                            session=session,
                            upsert=True
                        )
                        return
                    except OperationFailure as e:
                        if e.has_error_label("TransientTransactionError"):
                            await asyncio.sleep(0.1 * (attempt + 1))
                            continue
                        else:
                            raise

        raise OperationFailure("Partner pairing failed after retries.")

    # ===================== STATS ======================

    async def get_active_chats(self) -> int:
        active_users = await self.users.count_documents(
            {"partner_id": {"$ne": None}}
        )
        return active_users // 2

    # ===================== GROUP TRACKING (FIXED) ======================

    async def add_group(self, chat_id: int, title: str):
        await self.groups.update_one(
            {"_id": chat_id},
            {"$setOnInsert": {"title": title}},
            upsert=True
        )

    async def remove_group(self, chat_id: int):
        await self.groups.delete_one({"_id": chat_id})

    async def get_all_groups(self):
        cursor = self.groups.find({})
        return [doc async for doc in cursor]

    async def get_total_groups(self) -> int:
        return await self.groups.count_documents({})

    # ===================== AI SETTINGS ======================

    async def get_ai_status(self, chat_id: int) -> bool:
        settings = await self.ai_settings.find_one({"_id": chat_id})
        return bool(settings and settings.get("ai_enabled", False))

    async def set_ai_status(self, chat_id: int, status: bool):
        await self.ai_settings.update_one(
            {"_id": chat_id},
            {"$set": {"ai_enabled": status}},
            upsert=True
        )

    async def get_all_ai_enabled_chats(self) -> Set[int]:
        cursor = self.ai_settings.find({"ai_enabled": True})
        return {doc["_id"] async for doc in cursor}

    # ===================== AUTODELETE ======================

    async def get_autodelete_status(self, chat_id: int) -> bool:
        settings = await self.autodelete_settings.find_one({"_id": chat_id})
        return bool(settings and settings.get("autodelete_enabled", False))

    async def set_autodelete_status(self, chat_id: int, status: bool):
        await self.autodelete_settings.update_one(
            {"_id": chat_id},
            {"$set": {"autodelete_enabled": status}},
            upsert=True
        )

    async def get_all_autodelete_enabled_chats(self) -> Set[int]:
        cursor = self.autodelete_settings.find({"autodelete_enabled": True})
        return {doc["_id"] async for doc in cursor}

    # ===================== INSTAGRAM SESSION ======================

    async def get_insta_session(self, bot_session_name: str):
        return await self.insta_sessions.find_one({"_id": bot_session_name})

    async def save_insta_session(self, bot_session_name: str, settings: dict):
        await self.insta_sessions.update_one(
            {"_id": bot_session_name},
            {"$set": {"settings": settings}},
            upsert=True
        )

    async def delete_insta_session(self, bot_session_name: str):
        await self.insta_sessions.delete_one({"_id": bot_session_name})

    # ===================== FORWARDER CHECKPOINT ======================

    async def get_forwarder_checkpoint(self, source_id):
        """Get the last index processed for a source channel."""
        try:
            data = await self.col.find_one({"_id": "forwarder_checkpoint"})
            if data:
                return data.get(str(source_id), 0)
            return 0
        except Exception:
            return 0

    async def save_forwarder_checkpoint(self, source_id, index):
        """Save the last index processed for a source channel."""
        try:
            await self.col.update_one(
                {"_id": "forwarder_checkpoint"},
                {"$set": {str(source_id): index}},
                upsert=True
            )
        except Exception as e:
            print(f"[DB] Failed to save checkpoint: {e}")


# ------------------- Shared Instance -------------------

db = Database(MONGO_URI, MONGO_DB_NAME)
