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
    """تابع کمکی یکپارچه برای اتصال امن بدون مشکل با کاراکترهای خاص مثل @"""
    return await asyncpg.connect(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
    )

async def init_db():
    """ساخت جداول مورد نیاز ربات در صورت عدم وجود در دیتابیس ابری Supabase"""
    conn = await get_connection()
    
    # ۱. جدول وضعیت کاربران و ردیابی هدف‌های ریپلای (FSM)
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
    
    await conn.close()
    print("🚀 All Supabase tables initialized successfully.")


# ────────────────────────────────────────────────────────
# ⚙️ توابع مدیریت وضعیت کاربران (User States)
# ────────────────────────────────────────────────────────

async def get_user_state(user_id: int):
    """دریافت وضعیت فعلی و آیدی هدف ریپلای برای کاربر از دیتابیس ابری"""
    conn = await get_connection()
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
    conn = await get_connection()
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
    conn = await get_connection()
    await conn.execute("DELETE FROM user_states WHERE user_id = $1", user_id)
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




async def get_user_profile_stats(user_id: int) -> dict:
    """محاسبه و دریافت آمار دقیق پروفایل چت ناشناس و گروه برای یک کاربر"""
    conn = await get_connection()
    
    # ۱. تعداد کدهای ارسالی در گروه خودتان (۲۴ ساعت گذشته)
    sent_group_msgs = await conn.fetchval(
        "SELECT COUNT(*) FROM group_logs WHERE user_id = $1", user_id
    )
    
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
        "sent": sent_group_msgs,
        "received": received_anon_msgs,
        "blocked": blocked_count
    }