import asyncio  # <-- THIS IS THE MISSING LINE
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError, OperationFailure
from config import MONGO_URI, MONGO_DB_NAME

class Database:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]
        self.ai_settings = self.db["ai_settings"] 

    # ------------------- Connection -------------------
    async def connect(self):
        await self.client.server_info()

    async def close(self):
        self.client.close()

    # ------------------- User CRUD -------------------
    async def add_user(self, user_id: int, profile: dict):
        """
        Add a new user OR update existing profile.
        Keeps partner_id and status intact if user exists.
        """
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
        """
        Gets a user from the database.
        Returns the user document if found, otherwise returns None.
        """
        return await self.users.find_one({"_id": user_id})

    # ------------------- Status -------------------
    async def update_status(self, user_id: int, status: str):
        await self.users.update_one({"_id": user_id}, {"$set": {"status": status}})

    # ------------------- Partners -------------------
    async def set_partner(self, user_id: int, partner_id: int):
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": partner_id}})

    async def reset_partner(self, user_id: int):
        """
        Reset partner for a single user.
        """
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": None}})

    async def reset_partners(self, user1: int, user2: int):
        """
        Reset partners for both users at once.
        """
        await self.reset_partner(user1)
        await self.reset_partner(user2)


    async def set_partners_atomic(self, user1: int, user2: int):
        """
        Set partners for two users atomically using a MongoDB transaction with retry logic.
        """
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
                        # If both updates succeed, we can break the loop
                        return 
                    except OperationFailure as e:
                        # Check if it's a transient write conflict
                        if e.has_error_label("TransientTransactionError"):
                            print(f"DB Write Conflict (attempt {attempt + 1}/{max_retries}). Retrying...")
                            # Wait a short, random time before retrying to avoid another conflict
                            await asyncio.sleep(0.1 * (attempt + 1)) 
                            continue # Retry the loop
                        else:
                            # It's a different, non-retryable error
                            print(f"Failed to set partners atomically: {e}")
                            raise # Re-raise the error
        # If we get here, all retries failed
        print(f"Failed to set partners after {max_retries} attempts.")
        raise OperationFailure("Could not complete partner pairing after multiple retries.")

    # ------------------- Group Settings (AI) -------------------
    async def get_ai_status(self, chat_id: int) -> bool:
        """Checks if AI is enabled for a specific group using _id as the key."""
        settings = await self.ai_settings.find_one({"_id": chat_id})
        # If settings exist, return its status; otherwise, default to False
        return settings.get("ai_enabled", False) if settings else False

    async def set_ai_status(self, chat_id: int, status: bool):
        """Enables or disables AI for a specific group using _id as the key."""
        await self.ai_settings.update_one(
            {"_id": chat_id}, # ✅ Using _id (chat_id) for faster lookup
            {"$set": {"ai_enabled": status}},
            upsert=True
        )


# ------------------- Shared instance -------------------
db = Database(MONGO_URI, MONGO_DB_NAME)
