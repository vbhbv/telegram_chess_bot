import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
db_pool = None

async def init_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=10)
        async with db_pool.acquire() as conn:
            # جدول المستخدمين والتقييمات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    rating INT DEFAULT 1200,
                    wins INT DEFAULT 0,
                    losses INT DEFAULT 0,
                    draws INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # جدول المباريات النشطة والتاريخية
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    game_id VARCHAR(64) PRIMARY KEY,
                    white_player_id BIGINT,
                    black_player_id BIGINT,
                    fen TEXT NOT NULL,
                    moves TEXT DEFAULT '',
                    status VARCHAR(32) DEFAULT 'active',
                    winner_id BIGINT,
                    game_mode VARCHAR(32) DEFAULT 'pvp',
                    difficulty INT DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

async def get_db_pool():
    global db_pool
    if db_pool is None:
        await init_db_pool()
    return db_pool

async def close_db_pool():
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
      
