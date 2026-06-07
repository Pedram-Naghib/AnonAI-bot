import os
import string
import secrets
import asyncpg
import json
from datetime import datetime, timedelta, timezone

# ==========================================
# ⚙️ بخش ویژه: تنظیمات متمرکز اقتصادی ربات
# ==========================================
BASE_CHAT_COST = 0       # هزینه پایه ورود به چت تصادفی
GENDER_FILTER_COST = 3   # هزینه اضافه برای فیلتر جنسیت

# ==========================================
# ⚙️ تنظیمات دیتابیس 
# ==========================================
DB_USER = "postgres.yismztfpjnocbeyberdj"
DB_PASS = os.getenv("DB_PASS")
DB_HOST = "aws-1-eu-central-1.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"

DB_POOL = None

async def get_connection_pool():
    """ساخت یا دریافت پول اتصالات متمرکز دیتابیس جهت بهینه‌سازی کانکشن‌ها"""
    global DB_POOL
    if DB_POOL is None:
        DB_POOL = await asyncpg.create_pool(
            user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT, database=DB_NAME,
            min_size=5, max_size=20
        )
    return DB_POOL

async def get_connection():
    pool = await get_connection_pool()
    return await pool.acquire()

# ==========================================
# ⚖️ متد اصلی مقداردهی جداول و ایندکس‌ها
# ==========================================
async def init_db():
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        # ۱. جدول متمرکز و جامع کاربران
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, first_name TEXT, username TEXT, anon_state TEXT DEFAULT 'normal',
                reply_target_id BIGINT DEFAULT NULL, coins BIGINT DEFAULT 10, rating FLOAT DEFAULT 5.0,
                rating_count INT DEFAULT 0, chat_status TEXT DEFAULT 'idle', active_partner_id BIGINT DEFAULT NULL,
                queue_joined_at TIMESTAMPTZ DEFAULT NULL, last_compensation_at TIMESTAMPTZ DEFAULT NULL,
                last_daily_bonus_at TIMESTAMPTZ DEFAULT NULL, referred_by BIGINT DEFAULT NULL,
                is_ref_rewarded BOOLEAN DEFAULT FALSE, gender TEXT DEFAULT NULL,
                target_gender TEXT DEFAULT 'any', joined_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # پاتک تضمینی برای آپدیت ساختار دیتابیس‌های قدیمی
        alter_queries = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT DEFAULT NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_ref_rewarded BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS rating FLOAT DEFAULT 5.0;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS rating_count INT DEFAULT 0;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender TEXT DEFAULT NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS target_gender TEXT DEFAULT 'any';",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily_bonus_at TIMESTAMPTZ DEFAULT NULL;"
        ]
        for query in alter_queries:
            await conn.execute(query)

        # ۲. جداول مربوط به لینک‌ها، لیست سیاه و مسیریابی پیام‌ها
        await conn.execute("CREATE TABLE IF NOT EXISTS user_links (user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE, short_code VARCHAR(12) PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW())")
        await conn.execute("CREATE TABLE IF NOT EXISTS random_chat_blocks (user_id BIGINT, blocked_partner_id BIGINT, PRIMARY KEY (user_id, blocked_partner_id))")
        await conn.execute("CREATE TABLE IF NOT EXISTS message_map (user_chat_id BIGINT, user_msg_id BIGINT, anon_sender_id BIGINT, anon_msg_id BIGINT, PRIMARY KEY (user_chat_id, user_msg_id))")
        await conn.execute("CREATE TABLE IF NOT EXISTS block_list (owner_id BIGINT, blocked_id BIGINT, PRIMARY KEY (owner_id, blocked_id))")
        
        # ۳. ساخت ایندکس‌های فوق‌سریع
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_matchmaking_core ON users (chat_status, rating DESC, queue_joined_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_links_code ON user_links (short_code);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_msgmap_lookup ON message_map (user_chat_id, user_msg_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_msgmap_sender ON message_map (anon_sender_id, anon_msg_id);")
        
    print("🚀 All Unified Supabase pools, indexes & Database layers initialized successfully.")

# ────────────────────────────────────────────────────────
# 👤 توابع مدیریت کاربر و وضعیت (User Core & FSM)
# ────────────────────────────────────────────────────────
async def register_or_update_user(user_id: int, first_name: str, username: str):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO users (user_id, first_name, username) VALUES ($1, $2, $3) ON CONFLICT(user_id) DO UPDATE SET first_name = EXCLUDED.first_name, username = EXCLUDED.username", user_id, first_name, username)

async def get_user_state(user_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT anon_state, reply_target_id FROM users WHERE user_id = $1", user_id)
        return (row['anon_state'], row['reply_target_id']) if row else ("normal", None)

async def set_user_state(user_id: int, state: str, reply_target_id: int = None):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO users (user_id, anon_state, reply_target_id) VALUES ($1, $2::TEXT, $3::BIGINT) ON CONFLICT(user_id) DO UPDATE SET anon_state = EXCLUDED.anon_state, reply_target_id = EXCLUDED.reply_target_id", user_id, state, reply_target_id)

async def clear_user_state(user_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET anon_state = 'normal', reply_target_id = NULL WHERE user_id = $1", user_id)

async def get_complete_user_context(user_id: int) -> dict:
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT u.chat_status, u.active_partner_id, u.anon_state, u.reply_target_id, u.coins, u.gender, ul.short_code FROM users u LEFT JOIN user_links ul ON u.user_id = ul.user_id WHERE u.user_id = $1", user_id)
        if row:
            return {"chat_status": row['chat_status'], "active_partner_id": row['active_partner_id'], "anon_state": row['anon_state'], "reply_target_id": row['reply_target_id'], "coins": row['coins'], "gender": row['gender'], "short_code": row['short_code']}
        return {"chat_status": "idle", "active_partner_id": None, "anon_state": "normal", "reply_target_id": None, "coins": 10, "gender": None, "short_code": None}

async def get_user_id_by_username(username: str):
    clean_username = username.strip().lstrip('@')
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT user_id FROM users WHERE username ILIKE $1", clean_username)

# ────────────────────────────────────────────────────────
# 🔗 موتور مدیریت لینک‌های فوق‌کوتاه اختصاصی دیتابیس
# ────────────────────────────────────────────────────────
async def get_or_create_short_link(user_id: int) -> str:
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT short_code FROM user_links WHERE user_id = $1", user_id)
        if existing: return existing

        alphabet = string.ascii_letters + string.digits
        while True:
            short_code = ''.join(secrets.choice(alphabet) for _ in range(8))
            if not await conn.fetchval("SELECT 1 FROM user_links WHERE short_code = $1", short_code):
                break
        await conn.execute("INSERT INTO user_links (user_id, short_code) VALUES ($1, $2)", user_id, short_code)
        return short_code

async def get_user_id_by_short_code(short_code: str):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT user_id FROM user_links WHERE short_code = $1", short_code)

# ────────────────────────────────────────────────────────
# ⛓️ مدیریت نقشه‌برداری پیام‌های پیوی ناشناس (Message Mapping و Block)
# ────────────────────────────────────────────────────────
async def save_message_mapping(user_chat_id: int, user_msg_id: int, anon_sender_id: int, anon_msg_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO message_map (user_chat_id, user_msg_id, anon_sender_id, anon_msg_id) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING", user_chat_id, user_msg_id, anon_sender_id, anon_msg_id)

async def get_anon_sender_by_msg(user_chat_id: int, user_msg_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT anon_sender_id, anon_msg_id FROM message_map WHERE user_chat_id = $1 AND user_msg_id = $2", user_chat_id, user_msg_id)
        return (row['anon_sender_id'], row['anon_msg_id']) if row else None

async def get_super_user_by_msg(anon_sender_id: int, anon_msg_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_chat_id, user_msg_id FROM message_map WHERE anon_sender_id = $1 AND anon_msg_id = $2", anon_sender_id, anon_msg_id)
        return (row['user_chat_id'], row['user_msg_id']) if row else None

async def block_user(owner_id: int, blocked_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO block_list (owner_id, blocked_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", owner_id, blocked_id)

async def is_user_blocked(owner_id: int, blocked_id: int) -> bool:
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT 1 FROM block_list WHERE owner_id = $1 AND blocked_id = $2", owner_id, blocked_id) is not None

# ────────────────────────────────────────────────────────
# 📊 لایه محاسباتی آمار و پروفایل کاربری (Profile Stats)
# ────────────────────────────────────────────────────────
async def get_user_profile_stats(user_id: int) -> dict:
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        user_info = await conn.fetchrow("SELECT coins, rating, gender FROM users WHERE user_id = $1", user_id)
        received_anon_msgs = await conn.fetchval("SELECT COUNT(*) FROM message_map WHERE user_chat_id = $1", user_id)
        sent_anon_msgs = await conn.fetchval("SELECT COUNT(*) FROM message_map WHERE anon_sender_id = $1", user_id)
        blocked_count = await conn.fetchval("SELECT COUNT(*) FROM block_list WHERE owner_id = $1", user_id)
        
        return {
            "coins": user_info['coins'] if user_info else 10,
            "rating": user_info['rating'] if user_info else 5.0,
            "gender": user_info['gender'] if user_info else None,
            "received": received_anon_msgs,
            "sent": sent_anon_msgs,
            "blocked": blocked_count
        }

async def update_user_gender(user_id: int, gender: str):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET gender = $2::TEXT WHERE user_id = $1", user_id, gender)

# ────────────────────────────────────────────────────────
# 🎲 هستهٔ مرکزی، چت تصادفی و اقتصاد
# ────────────────────────────────────────────────────────
async def get_user_chat_status_ext(user_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT chat_status, active_partner_id, coins, gender FROM users WHERE user_id = $1", user_id)
        return (row['chat_status'], row['active_partner_id'], row['coins'], row['gender']) if row else ('idle', None, 10, None)

async def join_random_chat_queue(user_id: int, target_gender: str):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        cost = BASE_CHAT_COST + (GENDER_FILTER_COST if target_gender in ['male', 'female'] else 0)
        await conn.execute("UPDATE users SET chat_status = 'searching', queue_joined_at = NOW(), target_gender = $2::TEXT, coins = coins - $3 WHERE user_id = $1", user_id, target_gender, cost)

async def leave_random_chat_queue(user_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT target_gender FROM users WHERE user_id = $1", user_id)
        if row:
            refund = BASE_CHAT_COST + (GENDER_FILTER_COST if row['target_gender'] in ['male', 'female'] else 0)
            await conn.execute("UPDATE users SET chat_status = 'idle', queue_joined_at = NULL, active_partner_id = NULL, coins = coins + $2 WHERE user_id = $1", user_id, refund)

async def try_matchmaking(user_id: int, stage: int) -> int:
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        my_info = await conn.fetchrow("SELECT rating, gender, target_gender FROM users WHERE user_id = $1", user_id)
        if not my_info: return None
            
        my_rating, my_gender, my_target = my_info['rating'] or 5.0, my_info['gender'] or 'male', my_info['target_gender'] or 'any'
        
        rating_query = "AND u.rating BETWEEN $2 - 0.2 AND $2 + 0.2" if stage == 1 else ("AND u.rating BETWEEN $2 - 1.0 AND $2 + 1.0" if stage == 2 else "")
        gender_filter = "AND (($3 = 'any' AND (u.target_gender = 'any' OR u.target_gender = $4)) OR ($3 != 'any' AND u.gender = $3 AND (u.target_gender = 'any' OR u.target_gender = $4)))"
        
        base_query = f"""
            SELECT u.user_id FROM users u WHERE u.chat_status = 'searching' AND u.user_id != $1 {rating_query} {gender_filter}
              AND NOT EXISTS (SELECT 1 FROM random_chat_blocks rcb WHERE (rcb.user_id = $1 AND rcb.blocked_partner_id = u.user_id) OR (rcb.user_id = u.user_id AND rcb.blocked_partner_id = $1))
            ORDER BY u.rating DESC, u.queue_joined_at ASC LIMIT 1
        """
        return await conn.fetchval(base_query, user_id, my_rating, my_target, my_gender) if stage in [1, 2] else await conn.fetchval(base_query, user_id, my_target, my_gender)

async def connect_two_users(user1_id: int, user2_id: int) -> bool:
    low_id, high_id = sorted([user1_id, user2_id])
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            st_low = await conn.fetchval("SELECT chat_status FROM users WHERE user_id = $1 FOR UPDATE", low_id)
            st_high = await conn.fetchval("SELECT chat_status FROM users WHERE user_id = $1 FOR UPDATE", high_id)
            if st_low != 'searching' or st_high != 'searching':
                await tx.rollback()
                return False

            await conn.execute("UPDATE users SET chat_status = 'chatting', active_partner_id = $2, queue_joined_at = NULL WHERE user_id = $1", low_id, high_id)
            await conn.execute("UPDATE users SET chat_status = 'chatting', active_partner_id = $2, queue_joined_at = NULL WHERE user_id = $1", high_id, low_id)
            
            for uid in [user1_id, user2_id]:
                ref = await conn.fetchrow("SELECT referred_by, is_ref_rewarded FROM users WHERE user_id = $1", uid)
                if ref and ref['referred_by'] and not ref['is_ref_rewarded']:
                    await conn.execute("UPDATE users SET coins = coins + 5 WHERE user_id = $1", ref['referred_by'])
                    await conn.execute("UPDATE users SET is_ref_rewarded = TRUE WHERE user_id = $1", uid)
            
            await tx.commit()
            return True
        except Exception as e:
            await tx.rollback()
            print(f"💥 safe transaction match failed: {e}")
            return False

async def disconnect_active_chat(user_id: int) -> int:
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        partner_id = await conn.fetchval("SELECT active_partner_id FROM users WHERE user_id = $1", user_id)
        if partner_id:
            await conn.execute("UPDATE users SET chat_status = 'idle', active_partner_id = NULL WHERE user_id IN ($1, $2)", user_id, partner_id)
        return partner_id

async def apply_queue_compensation(user_id: int) -> str:
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT target_gender, last_compensation_at FROM users WHERE user_id = $1", user_id)
        if not row: return "failed"
            
        refund = BASE_CHAT_COST + (GENDER_FILTER_COST if row['target_gender'] in ['male', 'female'] else 0)
        
        # 🔥 همگام‌سازی منطق زمانی با تایم‌زون TIMESTAMPTZ سرور سوپابیس
        now = datetime.now(timezone.utc)
        last_comp = row['last_compensation_at']
        if last_comp and last_comp.tzinfo is None:
            last_comp = last_comp.replace(tzinfo=timezone.utc)

        if last_comp and now - last_comp < timedelta(hours=3):
            await conn.execute("UPDATE users SET chat_status = 'idle', queue_joined_at = NULL, coins = coins + $2 WHERE user_id = $1", user_id, refund)
            return "cooldown"
            
        await conn.execute("UPDATE users SET chat_status = 'idle', queue_joined_at = NULL, coins = coins + $2 + 2, last_compensation_at = NOW() WHERE user_id = $1", user_id, refund)
        return "rewarded"

# ────────────────────────────────────────────────────────
# ⭐ موتور آنتی‌ترول و پاداش‌های اقتصادی
# ────────────────────────────────────────────────────────
async def submit_user_rating(target_id: int, is_like: bool, voter_id: int):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT rating, rating_count FROM users WHERE user_id = $1", target_id)
        if row:
            current_rating, current_count = row['rating'] or 5.0, row['rating_count'] or 0
            new_rating = max(1.0, min(5.0, ((current_rating * current_count) + (5.0 if is_like else 1.0)) / (current_count + 1)))
            await conn.execute("UPDATE users SET rating = $1, rating_count = rating_count + 1 WHERE user_id = $2", new_rating, target_id)
            
        await conn.execute("UPDATE users SET coins = coins + 1 WHERE user_id = $1", voter_id)

async def add_to_chat_history_match(user_id: int, partner_id: int, status_type: str):
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        if status_type == "dislike":
            await conn.execute("INSERT INTO random_chat_blocks (user_id, blocked_partner_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", user_id, partner_id)

async def claim_daily_bonus(user_id: int) -> str:
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT last_daily_bonus_at FROM users WHERE user_id = $1", user_id)
        
        now = datetime.now(timezone.utc)
        
        if row and row['last_daily_bonus_at']:
            last_bonus = row['last_daily_bonus_at']
            if last_bonus.tzinfo is None:
                last_bonus = last_bonus.replace(tzinfo=timezone.utc)
                
            if now - last_bonus < timedelta(days=1):
                time_left = timedelta(days=1) - (now - last_bonus)
                hours, remainder = divmod(time_left.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                return f"cooldown_{hours:02d}:{minutes:02d}"
                
        await conn.execute("UPDATE users SET coins = coins + 5, last_daily_bonus_at = NOW() WHERE user_id = $1", user_id)
        return "rewarded"

async def set_user_referrer(user_id: int, referrer_id: int, is_pure_ref: bool = False):
    """ثبت آیدی معرف برای کاربر جدید در صورت صحت شرایط رفرال"""
    pool = await get_connection_pool()
    async with pool.acquire() as conn:
        current_ref = await conn.fetchval("SELECT referred_by FROM users WHERE user_id = $1", user_id)
        if not current_ref and user_id != referrer_id:
            await conn.execute("UPDATE users SET referred_by = $2 WHERE user_id = $1", user_id, referrer_id)
            
            # 🔥 اصلاح منطق مارکتینگ: اگر کاربر جدید باشد کیف پولش ۱۵ تایی می‌شود
            # اگر قدیمی باشد به پاس احترام به او سکه هدیه اضافه می‌گردد
            if is_pure_ref:
                await conn.execute("UPDATE users SET coins = 15 WHERE user_id = $1", user_id)
            else:
                await conn.execute("UPDATE users SET coins = coins + 5 WHERE user_id = $1", user_id)