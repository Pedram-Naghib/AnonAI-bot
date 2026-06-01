import os
import asyncpg
from datetime import datetime, timedelta

# خواندن آدرس اتصال مستقیم دیتابیس ابری سوپابیس از متغیرهای محیطی رندر
DATABASE_URL = os.getenv("DATABASE_URL")

async def init_db():
    """ساخت جداول مورد نیاز ربات در صورت عدم وجود در دیتابیس ابری Supabase"""
    conn = await asyncpg.connect(DATABASE_URL)
    
    # ۱. جدول وضعیت کاربران و ردیابی هدف‌های ریپلای (FSM) - تبدیل آیدی‌ها به BIGINT
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_states (
            user_id BIGINT PRIMARY KEY,
            state TEXT,
            reply_target_id BIGINT
        )
    """)
    
    # ۲. جدول نگاشت پیام‌ها برای انتقال ری‌آکشن‌ها
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
    
    # 📊 ۴. جدول مانیتورینگ طنز رفتارهای اعضا (سیستم آنالیز ۲۴ ساعته)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS group_logs (
            user_id BIGINT,
            username TEXT,
            first_name TEXT,
            message_text TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    await conn.close()
    print("🚀 All Supabase tables initialized successfully.")


# ────────────────────────────────────────────────────────
# ⚙️ توابع مدیریت وضعیت کاربران (User States)
# ────────────────────────────────────────────────────────

async def get_user_state(user_id: int):
    """دریافت وضعیت فعلی و آیدی هدف ریپلای برای کاربر از دیتابیس ابری"""
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow(
        "SELECT state, reply_target_id FROM user_states WHERE user_id = $1", 
        user_id
    )
    await conn.close()
    if row:
        return row['state'], row['reply_target_id']
    return "normal", None

async def set_user_state(user_id: int, state: str, reply_target_id: int = None):
    """تنظیم یا به‌روزرسانی وضعیت یک کاربر با ساختار جایگزینی همگام PostgreSQL"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO user_states (user_id, state, reply_target_id)
        VALUES ($1, $2, $3)
        ON CONFLICT(user_id) DO UPDATE SET 
            state = EXCLUDED.state, 
            reply_target_id = EXCLUDED.reply_target_id
    """, user_id, state, reply_target_id)
    await conn.close()

async def clear_user_state(user_id: int):
    """حذف وضعیت کاربر و بازگرداندن به حالت پیش‌فرض"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DELETE FROM user_states WHERE user_id = $1", user_id)
    await conn.close()


# ────────────────────────────────────────────────────────
# ⛓️ توابع مدیریت نقشه‌برداری پیام‌ها (Message Mapping)
# ────────────────────────────────────────────────────────

async def save_message_mapping(user_chat_id: int, user_msg_id: int, anon_sender_id: int, anon_msg_id: int):
    """ذخیره ارتباط پیام دریافت شده با پیام اصلی فرستنده"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO message_map (user_chat_id, user_msg_id, anon_sender_id, anon_msg_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT DO NOTHING
    """, user_chat_id, user_msg_id, anon_sender_id, anon_msg_id)
    await conn.close()

async def get_anon_sender_by_msg(user_chat_id: int, user_msg_id: int):
    """پیدا کردن اطلاعات پیام فرستنده اصلی بر اساس پیام دریافتی شما"""
    conn = await asyncpg.connect(DATABASE_URL)
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
    conn = await asyncpg.connect(DATABASE_URL)
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
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO block_list (owner_id, blocked_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
    """, owner_id, blocked_id)
    await conn.close()

async def is_user_blocked(owner_id: int, blocked_id: int) -> bool:
    """بررسی وضعیت بلاک بودن فرستنده ناشناس"""
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("""
        SELECT 1 FROM block_list 
        WHERE owner_id = $1 AND blocked_id = $2
    """, owner_id, blocked_id)
    await conn.close()
    return row is not None


# ────────────────────────────────────────────────────────
# 📊 سیستم مانیتورینگ طنز رفتارهای اعضا (PostgreSQL Cloud Compatible)
# ────────────────────────────────────────────────────────

async def log_message_to_db(user_id: int, username: str, first_name: str, text: str):
    """ذخیره ناهمگام چت‌های عادی اعضای گروه درون جدول دیتابیس ابری"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO group_logs (user_id, username, first_name, message_text, timestamp) VALUES ($1, $2, $3, $4, $5)",
        user_id, username, first_name, text, datetime.now()
    )
    await conn.close()

async def get_daily_group_logs():
    """استخراج ناهمگام پیام‌های ۲۴ ساعت گذشته گروه بر اساس فرمت زمان بومی"""
    one_day_ago = datetime.now() - timedelta(days=1)
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("""
        SELECT first_name, username, message_text 
        FROM group_logs 
        WHERE timestamp > $1
    """, one_day_ago)
    await conn.close()
    # تبدیل به فرمت لیست از چندجمله‌ای‌ها (Tuple) جهت همگام‌سازی با بخش‌های قبلی برنامه
    return [(r['first_name'], r['username'], r['message_text']) for r in rows]

async def clean_old_logs():
    """حذف اتوماتیک پیام‌های قدیمی گروه برای بهینه‌سازی حجم دیتابیس رایگان Supabase"""
    two_days_ago = datetime.now() - timedelta(days=2)
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DELETE FROM group_logs WHERE timestamp < $1", two_days_ago)
    await conn.close()