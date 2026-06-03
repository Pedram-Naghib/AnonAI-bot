import os
import asyncpg
from datetime import datetime, timedelta

DB_USER = "postgres.yismztfpjnocbeyberdj"
DB_PASS = os.getenv("DB_PASS")
DB_HOST = "aws-1-eu-central-1.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"

async def get_connection():
    return await asyncpg.connect(
        user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT, database=DB_NAME
    )

async def init_db():
    conn = await get_connection()
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            anon_state TEXT DEFAULT 'normal',
            reply_target_id BIGINT DEFAULT NULL,
            coins BIGINT DEFAULT 10,
            rating FLOAT DEFAULT 5.0,
            rating_count INT DEFAULT 0,
            chat_status TEXT DEFAULT 'idle',
            active_partner_id BIGINT DEFAULT NULL,
            queue_joined_at TIMESTAMPTZ DEFAULT NULL,
            last_compensation_at TIMESTAMPTZ DEFAULT NULL,
            referred_by BIGINT DEFAULT NULL,
            is_ref_rewarded BOOLEAN DEFAULT FALSE,
            gender TEXT DEFAULT NULL,
            target_gender TEXT DEFAULT 'any',
            joined_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT DEFAULT NULL;")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_ref_rewarded BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS rating FLOAT DEFAULT 5.0;")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS rating_count INT DEFAULT 0;")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender TEXT DEFAULT NULL;")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS target_gender TEXT DEFAULT 'any';")
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS random_chat_blocks (
            user_id BIGINT,
            blocked_partner_id BIGINT,
            PRIMARY KEY (user_id, blocked_partner_id)
        )
    """)
    
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_matchmaking_core 
        ON users (chat_status, rating DESC, queue_joined_at)
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS message_map (
            user_chat_id BIGINT,
            user_msg_id BIGINT,
            anon_sender_id BIGINT,
            anon_msg_id BIGINT,
            PRIMARY KEY (user_chat_id, user_msg_id)
        )
    """)
    
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS block_list (
            owner_id BIGINT,
            blocked_id BIGINT,
            PRIMARY KEY (owner_id, blocked_id)
        )
    """)
    
    await conn.close()
    print("🚀 All Unified Supabase tables & Gender Match layers initialized successfully.")

async def register_or_update_user(user_id: int, first_name: str, username: str):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO users (user_id, first_name, username)
        VALUES ($1, $2, $3)
        ON CONFLICT(user_id) DO UPDATE SET first_name = EXCLUDED.first_name, username = EXCLUDED.username
    """, user_id, first_name, username)
    await conn.close()

async def get_user_state(user_id: int):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT anon_state, reply_target_id FROM users WHERE user_id = $1", user_id)
    await conn.close()
    if row:
        return row['anon_state'], row['reply_target_id']
    return "normal", None

async def set_user_state(user_id: int, state: str, reply_target_id: int = None):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO users (user_id, anon_state, reply_target_id)
        VALUES ($1, $2, $3)
        ON CONFLICT(user_id) DO UPDATE SET anon_state = EXCLUDED.anon_state, reply_target_id = EXCLUDED.reply_target_id
    """, user_id, state, reply_target_id)
    await conn.close()

async def clear_user_state(user_id: int):
    conn = await get_connection()
    await conn.execute("UPDATE users SET anon_state = 'normal', reply_target_id = NULL WHERE user_id = $1", user_id)
    await conn.close()

async def save_message_mapping(user_chat_id: int, user_msg_id: int, anon_sender_id: int, anon_msg_id: int):
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO message_map (user_chat_id, user_msg_id, anon_sender_id, anon_msg_id)
        VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
    """, user_chat_id, user_msg_id, anon_sender_id, anon_msg_id)
    await conn.close()

async def get_anon_sender_by_msg(user_chat_id: int, user_msg_id: int):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT anon_sender_id, anon_msg_id FROM message_map WHERE user_chat_id = $1 AND user_msg_id = $2", user_chat_id, user_msg_id)
    await conn.close()
    if row:
        return row['anon_sender_id'], row['anon_msg_id']
    return None

async def get_super_user_by_msg(anon_sender_id: int, anon_msg_id: int):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT user_chat_id, user_msg_id FROM message_map WHERE anon_sender_id = $1 AND anon_msg_id = $2", anon_sender_id, anon_msg_id)
    await conn.close()
    if row:
        return row['user_chat_id'], row['user_msg_id']
    return None

async def block_user(owner_id: int, blocked_id: int):
    conn = await get_connection()
    await conn.execute("INSERT INTO block_list (owner_id, blocked_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", owner_id, blocked_id)
    await conn.close()

async def is_user_blocked(owner_id: int, blocked_id: int) -> bool:
    conn = await get_connection()
    row = await conn.fetchrow("SELECT 1 FROM block_list WHERE owner_id = $1 AND blocked_id = $2", owner_id, blocked_id)
    await conn.close()
    return row is not None

async def get_user_profile_stats(user_id: int) -> dict:
    conn = await get_connection()
    user_info = await conn.fetchrow("SELECT coins, rating, gender FROM users WHERE user_id = $1", user_id)
    coins = user_info['coins'] if user_info else 10
    rating = user_info['rating'] if user_info else 5.0
    gender = user_info['gender'] if user_info else None
    
    received_anon_msgs = await conn.fetchval("SELECT COUNT(*) FROM message_map WHERE user_chat_id = $1", user_id)
    blocked_count = await conn.fetchval("SELECT COUNT(*) FROM block_list WHERE owner_id = $1", user_id)
    await conn.close()
    
    return {"coins": coins, "rating": rating, "received": received_anon_msgs, "blocked": blocked_count, "gender": gender}

async def update_user_gender(user_id: int, gender: str):
    conn = await get_connection()
    await conn.execute("UPDATE users SET gender = $2 WHERE user_id = $1", user_id, gender)
    await conn.close()

async def get_user_chat_status_ext(user_id: int):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT chat_status, active_partner_id, coins, gender FROM users WHERE user_id = $1", user_id)
    await conn.close()
    if row:
        return row['chat_status'], row['active_partner_id'], row['coins'], row['gender']
    return 'idle', None, 10, None

async def join_random_chat_queue(user_id: int, target_gender: str):
    conn = await get_connection()
    cost = 10 if target_gender in ['male', 'female'] else 0
    await conn.execute("""
        UPDATE users 
        SET chat_status = 'searching', queue_joined_at = NOW(), target_gender = $2, coins = coins - $3
        WHERE user_id = $1
    """, user_id, target_gender, cost)
    await conn.close()

async def leave_random_chat_queue(user_id: int):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT target_gender FROM users WHERE user_id = $1", user_id)
    if row:
        refund = 10 if row['target_gender'] in ['male', 'female'] else 0
        await conn.execute("""
            UPDATE users 
            SET chat_status = 'idle', queue_joined_at = NULL, active_partner_id = NULL, coins = coins + $2 
            WHERE user_id = $1
        """, user_id, refund)
    await conn.close()

async def try_matchmaking(user_id: int, stage: int) -> int:
    """الگوریتم مچ‌میکینگ پیشرفته با فیلترهای منطقی و ضربدری جنسیت طرفین چت"""
    conn = await get_connection()
    my_info = await conn.fetchrow("SELECT rating, gender, target_gender FROM users WHERE user_id = $1", user_id)
    
    if not my_info:
        await conn.close()
        return None
        
    my_rating = my_info['rating'] or 5.0
    my_gender = my_info['gender'] or 'male'
    my_target = my_info['target_gender'] or 'any'
    
    rating_query = "AND u.rating BETWEEN $2 - 0.2 AND $2 + 0.2" if stage == 1 else ("AND u.rating BETWEEN $2 - 1.0 AND $2 + 1.0" if stage == 2 else "")
    
    gender_filter = """
        AND (
            ($3 = 'any' AND (u.target_gender = 'any' OR u.target_gender = $4))
            OR
            ($3 != 'any' AND u.gender = $3 AND (u.target_gender = 'any' OR u.target_gender = $4))
        )
    """
    
    base_query = f"""
        SELECT u.user_id FROM users u
        WHERE u.chat_status = 'searching' AND u.user_id != $1 
          {rating_query}
          {gender_filter}
          AND NOT EXISTS (
              SELECT 1 FROM random_chat_blocks rcb 
              WHERE (rcb.user_id = $1 AND rcb.blocked_partner_id = u.user_id)
                 OR (rcb.user_id = u.user_id AND rcb.blocked_partner_id = $1)
          )
        ORDER BY u.rating DESC, u.queue_joined_at ASC LIMIT 1
    """
    
    # 🎯 اصلاح خطای سینتکس خط ۲۳۶: کوئری به صورت کامل همراه با پارامترها با متد fetchval فراخوانی شد
    if stage in [1, 2]:
        partner_id = await conn.fetchval(base_query, user_id, my_rating, my_target, my_gender)
    else:
        partner_id = await conn.fetchval(base_query, user_id, my_target, my_gender)
        
    await conn.close()
    return partner_id

async def connect_two_users(user1_id: int, user2_id: int) -> bool:
    low_id, high_id = (user1_id, user2_id) if user1_id < user2_id else (user2_id, user1_id)
    conn = await get_connection()
    tx = conn.transaction()
    await tx.start()
    
    try:
        st_low = await conn.fetchval("SELECT chat_status FROM users WHERE user_id = $1 FOR UPDATE", low_id)
        st_high = await conn.fetchval("SELECT chat_status FROM users WHERE user_id = $1 FOR UPDATE", high_id)
        
        if st_low != 'searching' or st_high != 'searching':
            await tx.rollback()
            await conn.close()
            return False

        await conn.execute("UPDATE users SET chat_status = 'chatting', active_partner_id = $2, queue_joined_at = NULL WHERE user_id = $1", low_id, high_id if low_id == user1_id else user1_id)
        await conn.execute("UPDATE users SET chat_status = 'chatting', active_partner_id = $2, queue_joined_at = NULL WHERE user_id = $1", high_id, low_id if high_id == user1_id else user1_id)
        
        ref1 = await conn.fetchrow("SELECT referred_by, is_ref_rewarded FROM users WHERE user_id = $1", user1_id)
        if ref1 and ref1['referred_by'] and not ref1['is_ref_rewarded']:
            await conn.execute("UPDATE users SET coins = coins + 5 WHERE user_id = $1", ref1['referred_by'])
            await conn.execute("UPDATE users SET is_ref_rewarded = TRUE WHERE user_id = $1", user1_id)

        ref2 = await conn.fetchrow("SELECT referred_by, is_ref_rewarded FROM users WHERE user_id = $1", user2_id)
        if ref2 and ref2['referred_by'] and not ref2['is_ref_rewarded']:
            await conn.execute("UPDATE users SET coins = coins + 5 WHERE user_id = $1", ref2['referred_by'])
            await conn.execute("UPDATE users SET is_ref_rewarded = TRUE WHERE user_id = $1", user2_id)
        
        await tx.commit()
        await conn.close()
        return True
    except Exception as e:
        await tx.rollback()
        await conn.close()
        print(f"💥 Error in safe transaction connection: {e}")
        return False

async def disconnect_active_chat(user_id: int) -> int:
    conn = await get_connection()
    partner_id = await conn.fetchval("SELECT active_partner_id FROM users WHERE user_id = $1", user_id)
    if partner_id:
        await conn.execute("UPDATE users SET chat_status = 'idle', active_partner_id = NULL WHERE user_id = $1", user_id)
        await conn.execute("UPDATE users SET chat_status = 'idle', active_partner_id = NULL WHERE user_id = $1", partner_id)
    await conn.close()
    return partner_id

async def apply_queue_compensation(user_id: int) -> str:
    conn = await get_connection()
    row = await conn.fetchrow("SELECT target_gender, last_compensation_at FROM users WHERE user_id = $1", user_id)
    
    if not row:
        await conn.close()
        return "failed"
        
    target_gender = row['target_gender']
    last_comp = row['last_compensation_at']
    now = datetime.now()
    
    refund = 10 if target_gender in ['male', 'female'] else 0
    
    if last_comp and now - last_comp < timedelta(hours=3):
        await conn.execute("UPDATE users SET chat_status = 'idle', queue_joined_at = NULL, coins = coins + $2 WHERE user_id = $1", user_id, refund)
        await conn.close()
        return "cooldown"
        
    bonus = 2 if refund == 0 else 0 
    await conn.execute("""
        UPDATE users 
        SET chat_status = 'idle', queue_joined_at = NULL, coins = coins + $2 + $3, last_compensation_at = NOW() 
        WHERE user_id = $1
    """, user_id, refund, bonus)
    await conn.close()
    return "rewarded"

async def submit_user_rating(target_id: int, is_like: bool):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT rating, rating_count FROM users WHERE user_id = $1", target_id)
    if row:
        current_rating = row['rating'] or 5.0
        current_count = row['rating_count'] or 0
        new_score = 5.0 if is_like else 1.0
        new_count = current_count + 1
        new_rating = ((current_rating * current_count) + new_score) / new_count
        new_rating = max(1.0, min(5.0, new_rating))
        await conn.execute("UPDATE users SET rating = $2, rating_count = $3 WHERE user_id = $1", target_id, new_rating, new_count)
    await conn.close()

async def add_to_chat_history_match(user_id: int, partner_id: int, status_type: str):
    conn = await get_connection()
    if status_type == "dislike":
        await conn.execute("INSERT INTO random_chat_blocks (user_id, blocked_partner_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", user_id, partner_id)
    await conn.close()

async def set_user_referrer(user_id: int, referrer_id: int, is_pure_ref: bool = True):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT referred_by FROM users WHERE user_id = $1", user_id)
    
    if row:
        if row['referred_by'] is None and user_id != referrer_id:
            await conn.execute("UPDATE users SET referred_by = $2 WHERE user_id = $1", user_id, referrer_id)
    else:
        initial_coins = 15 if is_pure_ref else 10
        await conn.execute("""
            INSERT INTO users (user_id, referred_by, coins) 
            VALUES ($1, $2, $3)
            ON CONFLICT(user_id) DO UPDATE SET referred_by = $2
            WHERE users.referred_by IS NULL
        """, user_id, referrer_id, initial_coins)
        
    await conn.close()