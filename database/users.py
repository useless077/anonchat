# users.py
from motor.motor_asyncio import AsyncIOMotorClient

class Database:
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]  # Only users collection

    async def connect(self):
        # Test connection
        await self.client.server_info()

    async def close(self):
        self.client.close()

    # Add a new user or update if exists
    async def add_user(self, user_id: int, profile: dict):
        """
        profile = {
            "gender": "male/female/other",
            "age": 22,
            "location": "India",
            "dp": "file_id"
        }
        """
        await self.users.update_one(
            {"_id": user_id},
            {"$set": {"profile": profile, "status": "idle", "partner_id": None}},
            upsert=True
        )

    # Get user by id
    async def get_user(self, user_id: int):
        user = await self.users.find_one({"_id": user_id})
        if not user:
            # Return default empty structure if user not found
            return {"_id": user_id, "profile": {}, "status": "idle", "partner_id": None}
        return user

    # Update user status (idle / searching / chatting)
    async def update_status(self, user_id: int, status: str):
        await self.users.update_one({"_id": user_id}, {"$set": {"status": status}})

    # Set chat partner
    async def set_partner(self, user_id: int, partner_id: int):
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": partner_id}})

    # Reset chat partner
    async def reset_partner(self, user_id: int):
        await self.users.update_one({"_id": user_id}, {"$set": {"partner_id": None}})
