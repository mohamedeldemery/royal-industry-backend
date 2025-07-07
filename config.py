import asyncpg

# Database Connection URL
DATABASE_URL = "postgresql://postgres:123@192.168.1.200:5432/Royal Industry"

# Async database connection
async def connect_to_db():
    return await asyncpg.connect(DATABASE_URL)
