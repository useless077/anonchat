import asyncio
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure
from config import MONGO_URI, MONGO_DB_NAME

logger = logging.getLogger(__name__)

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
        self.forwarder_checkpoint = self.db["forwarder_checkpoint"]
        self.cache_col = self.db["bot_cache"]

    # ================= CONNECTION =================

    async def connect(self):
        await self.client.server_info()

    async def close(self):
        self.client.close()

    # ================= USERS =================

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

    async def get_user(self, user_id: int):
        return await self.users.find_one({"_id": user_id})

    async def get_all_users(self):
        cursor = self.users.find({}, {"_id": 1})
        return [doc["_id"] async for doc in cursor]

    async def remove_user(self, user_id: int):
        await self.users.delete_one({"_id": user_id})

    async def get_total_users(self):
        return await self.users.count_documents({})

    # ================= STATUS =================

    async def update_status(self, user_id: int, status: str):
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"status": status}},
            upsert=True
        )

    # ================= GROUPS =================

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

    async def get_total_groups(self):
        return await self.groups.count_documents({})

    # ================= FORWARDER =================

    async def get_forwarder_checkpoint(self, source_id):
        try:
            data = await self.forwarder_checkpoint.find_one({"_id": "forwarder_checkpoint"})
            return data.get(str(source_id), 0) if data else 0
        except:
            return 0

    async def save_forwarder_checkpoint(self, source_id, index):
        try:
            await self.forwarder_checkpoint.update_one(
                {"_id": "forwarder_checkpoint"},
                {"$set": {str(source_id): index}},
                upsert=True
            )
        except Exception as e:
            print(f"[DB] Checkpoint error: {e}")

    # ================= VIDEO CACHE =================

    async def get_video_list_db(self, source_id):
        try:
            data = await self.cache_col.find_one({"_id": f"video_list_{source_id}"})
            return list(data.get("ids", [])) if data else []
        except:
            return []

    async def save_video_list_db(self, source_id, video_ids):
        try:
            await self.cache_col.update_one(
                {"_id": f"video_list_{source_id}"},
                {"$set": {"ids": video_ids}},
                upsert=True
            )
        except Exception as e:
            print(f"[DB] Save error: {e}")

    # 🔥 FIXED FUNCTION (IMPORTANT)
    async def append_video_id(self, source_id, msg_id):
        try:
            result = await self.cache_col.update_one(
                {"_id": f"video_list_{source_id}"},
                {"$addToSet": {"ids": msg_id}},
                upsert=True
            )

            # ✅ True = new added, False = duplicate
            return result.modified_count > 0

        except Exception as e:
            print(f"[DB] Append error: {e}")
            return False

    # ================= MEDIA GROUP =================

    async def get_media_groups_db(self):
        try:
            data = await self.cache_col.find_one({"_id": "processed_media_groups"})
            return set(data["ids"]) if data and "ids" in data else set()
        except:
            return set()

    async def add_media_group_db(self, group_id):
        try:
            await self.cache_col.update_one(
                {"_id": "processed_media_groups"},
                {"$addToSet": {"ids": group_id}},
                upsert=True
            )
        except Exception as e:
            print(f"[DB] Media group error: {e}")


# ================= INSTANCE =================

db = Database(MONGO_URI, MONGO_DB_NAME)
