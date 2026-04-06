import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "incident_copilot")

client: AsyncIOMotorClient = None
db = None


async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DATABASE_NAME]

    # Create indexes
    await db.incidents.create_index("status")
    await db.incidents.create_index("severity")
    await db.incidents.create_index("createdAt")
    await db.logs.create_index("incidentId")
    await db.solutions.create_index("incidentId")
    await db.feedback.create_index("incidentId")


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return db
