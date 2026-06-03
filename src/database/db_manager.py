import os
import asyncpg
from datetime import datetime, timedelta

# ⚙️ تنظیمات تفکیک‌شده اتصال لایو به دیتابیس سوپابیس
DB_USER = "postgres.yismztfpjnocbeyberdj"
DB_PASS = os.getenv("DB_PASS")  # خواندن از لوکال یا سرور رندر
DB_HOST = "aws-1-eu-central-1.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"

async def get_connection():
    """تابع کمکی یکپارچه برای اتصال امن بدون مشکل با کاراکترهای خاص"""
    return await asyncpg.connect(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
    )

async def init_db():
    """ساخت جداول مینی‌مال و متمرکز ربات در صورت عدم وجود در دیتابیس ابری Supabase"""
    conn = await get_connection()
    
    # ۱. جدول جامع و متمرکز کاربران (ادغام اطلاعات هویتی، ماشین وضعیت FSM و اقتصاد سکه)
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
            joined_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    # ساخت ایندکس بهینه برای جستجوی فوق سریع در صف چت تصادفی
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_matchmaking_core 
        ON users (chat_status, rating DESC, queue_joined_at)
    """)
    
    # ۲. جدول نگاشت پیام‌ها برای انتقال پینگ‌پنگی چت ناشناس
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS message_map (
            user_chat_id BIGINT,
            user_msg_id BIGINT,
            anon_sender_id BIGINT,
            anon_msg_id BIGINT,
            PRIMARY KEY (user_chat_id, user_msg_id)
        )
    """)
    
    # ۳. جدول لیست سیاه (بلاک لیست کاربران ناشناس)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS block_list (
            owner_id BIGINT,
            blocked_id BIGINT,
            PRIMARY KEY (owner_id, blocked_id)
        )
    """)
    
    await conn.close()
    print("🚀 All Unified Supabase tables initialized successfully.")


# ────────────────────────────────────────────────────────
# 👤 توابع مدیریت هویت و وضعیت کاربران (User Core & FSM)
# ────────────────────────────────────────────────────────

async def register_or_update_user(user_id: int, first_name: str, username: str):
    """ثبت‌نام اولیه یا به‌روزرسانی اطلاعات هویتی کاربر در جدول مرجع"""
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO users (user_id, first_name, username)
        VALUES ($1, $2, $3)
        ON CONFLICT(user_id) DO UPDATE SET 
            first_name = EXCLUDED.first_name, 
            username = EXCLUDED.username
    """, user_id, first_name, username)
    await conn.close()

async def get_user_state(user_id: int):
    """دریافت وضعیت فعلی اف‌اس‌ام چت ناشناس و آیدی هدف ریپلای از جدول جامع users"""
    conn = await get_connection()
    row = await conn.fetchrow(
        "SELECT anon_state, reply_target_id FROM users WHERE user_id = $1", 
        user_id
    )
    await conn.close()
    if row:
        return row['anon_state'], row['reply_target_id']
    return "normal", None

async def set_user_state(user_id: int, state: str, reply_target_id: int = None):
    """تنظیم یا به‌روزرسانی وضعیت اف‌اس‌ام کاربر با ساختار اتمیک UPSERT"""
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO users (user_id, anon_state, reply_target_id)
        VALUES ($1, $2, $3)
        ON CONFLICT(user_id) DO UPDATE SET 
            anon_state = EXCLUDED.anon_state, 
            reply_target_id = EXCLUDED.reply_target_id
    """, user_id, state, reply_target_id)
    await conn.close()

async def clear_user_state(user_id: int):
    """بازگرداندن وضعیت چت ناشناس کاربر به حالت پیش‌فرض بدون حذف اکانت و سکه‌ها"""
    conn = await get_connection()
    await conn.execute("""
        UPDATE users 
        SET anon_state = 'normal', reply_target_id = NULL 
        WHERE user_id = $1
    """, user_id)
    await conn.close()


# ────────────────────────────────────────────────────────
# ⛓️ توابع مدیریت نقشه‌برداری پیام‌ها (Message Mapping)
# ────────────────────────────────────────────────────────

async def save_message_mapping(user_chat_id: int, user_msg_id: int, anon_sender_id: int, anon_msg_id: int):
    """ذخیره ارتباط پیام دریافت شده با پیام اصلی فرستنده"""
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO message_map (user_chat_id, user_msg_id, anon_sender_id, anon_msg_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT DO NOTHING
    """, user_chat_id, user_msg_id, anon_sender_id, anon_msg_id)
    await conn.close()

async def get_anon_sender_by_msg(user_chat_id: int, user_msg_id: int):
    """پیدا کردن اطلاعات پیام فرستنده اصلی بر اساس پیام دریافتی شما"""
    conn = await get_connection()
    row = await conn.fetchrow("""
        SELECT anon_sender_id, anon_msg_id 
        FROM message_map 
        WHERE user_chat_id = $1 AND user_msg_id = $2
    """, user_chat_id, user_msg_id)
    await conn.close()
    if row:
        return row['anon_sender_id'], row['anon_msg_id']
    return None

async def get_super_user_by_msg(anon_sender_id: int, anon_msg_id: int):
    """پیدا کردن اطلاعات پیام صاحب لینک (سوپریوزر) بر اساس پیام شخص غریبه"""
    conn = await get_connection()
    row = await conn.fetchrow("""
        SELECT user_chat_id, user_msg_id 
        FROM message_map 
        WHERE anon_sender_id = $1 AND anon_msg_id = $2
    """, anon_sender_id, anon_msg_id)
    await conn.close()
    if row:
        return row['user_chat_id'], row['user_msg_id']
    return None


# ────────────────────────────────────────────────────────
# 🚫 توابع مدیریت لیست سیاه (Block List)
# ────────────────────────────────────────────────────────

async def block_user(owner_id: int, blocked_id: int):
    """بلاک کردن دائمی یک کاربر ناشناس توسط صاحب لینک"""
    conn = await get_connection()
    await conn.execute("""
        INSERT INTO block_list (owner_id, blocked_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
    """, owner_id, blocked_id)
    await conn.close()

async def is_user_blocked(owner_id: int, blocked_id: int) -> bool:
    """بررسی وضعیت بلاک بودن فرستنده ناشناس"""
    conn = await get_connection()
    row = await conn.fetchrow("""
        SELECT 1 FROM block_list 
        WHERE owner_id = $1 AND blocked_id = $2
    """, owner_id, blocked_id)
    await conn.close()
    return row is not None


# ────────────────────────────────────────────────────────
# 📊 توابع محاسباتی و آمار پروفایل (Profile Stats)
# ────────────────────────────────────────────────────────

async def get_user_profile_stats(user_id: int) -> dict:
    """دریافت آمار دقیق هویتی، موجودی اقتصادی و چت ناشناس کاربر"""
    conn = await get_connection()
    
    # ۱. دریافت دارایی‌ها (سکه و امتیاز) از جدول مرکزی users
    user_info = await conn.fetchrow(
        "SELECT coins, rating FROM users WHERE user_id = $1", user_id
    )
    coins = user_info['coins'] if user_info else 10
    rating = user_info['rating'] if user_info else 5.0
    
    # ۲. تعداد پیام‌های ناشناسی که بقیه به لینک این کاربر فرستاده‌اند (دریافتی‌ها)
    received_anon_msgs = await conn.fetchval(
        "SELECT COUNT(*) FROM message_map WHERE user_chat_id = $1", user_id
    )
    
    # ۳. تعداد افرادی که این کاربر آن‌ها را بلاک کرده است
    blocked_count = await conn.fetchval(
        "SELECT COUNT(*) FROM block_list WHERE owner_id = $1", user_id
    )
    
    await conn.close()
    
    return {
        "coins": coins,
        "rating": rating,
        "received": received_anon_msgs,
        "blocked": blocked_count
    }