import aiosqlite

DB_PATH = "servant_bot.db"

async def init_db():
    """ساخت جداول مورد نیاز ربات در صورت عدم وجود"""
    async with aiosqlite.connect(DB_PATH) as db:
        
        # ۱. جدول وضعیت کاربران و ردیابی هدف‌های ریپلای (FSM)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                reply_target_id INTEGER
            )
        """)
        
        # ۲. جدول نگاشت پیام‌ها برای انتقال ری‌آکشن‌ها (با متغیرهای اختصاصی خودت)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS message_map (
                user_chat_id INTEGER,
                user_msg_id INTEGER,
                anon_sender_id INTEGER,
                anon_msg_id INTEGER,
                PRIMARY KEY (user_chat_id, user_msg_id)
            )
        """)
        
        # ۳. جدول لیست سیاه (بلاک لیست کاربران ناشناس)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS block_list (
                owner_id INTEGER,
                blocked_id INTEGER,
                PRIMARY KEY (owner_id, blocked_id)
            )
        """)
        
        await db.commit()


# ────────────────────────────────────────────────────────
# ⚙️ توابع مدیریت وضعیت کاربران (User States)
# ────────────────────────────────────────────────────────

async def get_user_state(user_id: int):
    """دریافت وضعیت فعلی و آیدی هدف ریپلای برای کاربر"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT state, reply_target_id FROM user_states WHERE user_id = ?", 
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0], row[1]
            return "normal", None

async def set_user_state(user_id: int, state: str, reply_target_id: int = None):
    """تنظیم یا به‌روزرسانی وضعیت یک کاربر در دیتابیس"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_states (user_id, state, reply_target_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                state = EXCLUDED.state, 
                reply_target_id = EXCLUDED.reply_target_id
        """, (user_id, state, reply_target_id))
        await db.commit()

async def clear_user_state(user_id: int):
    """حذف وضعیت کاربر و بازگرداندن به حالت پیش‌فرض (حذف سطر)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
        await db.commit()


# ────────────────────────────────────────────────────────
# ⛓️ توابع مدیریت نقشه‌برداری پیام‌ها (Message Mapping)
# ────────────────────────────────────────────────────────

async def save_message_mapping(user_chat_id: int, user_msg_id: int, anon_sender_id: int, anon_msg_id: int):
    """ذخیره ارتباط پیام دریافت شده با پیام اصلی فرستنده جهت اتصال ری‌آکشن‌ها"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO message_map (user_chat_id, user_msg_id, anon_sender_id, anon_msg_id)
            VALUES (?, ?, ?, ?)
        """, (user_chat_id, user_msg_id, anon_sender_id, anon_msg_id))
        await db.commit()

async def get_anon_sender_by_msg(user_chat_id: int, user_msg_id: int):
    """پیدا کردن اطلاعات پیام فرستنده اصلی بر اساس پیام دریافتی شما"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT anon_sender_id, anon_msg_id 
            FROM message_map 
            WHERE user_chat_id = ? AND user_msg_id = ?
        """, (user_chat_id, user_msg_id)) as cursor:
            return await cursor.fetchone()  # خروجی به صورت یک Tuple شامل (anon_sender_id, anon_msg_id) است


async def get_super_user_by_msg(anon_sender_id: int, anon_msg_id: int):
    """پیدا کردن اطلاعات پیام صاحب لینک (سوپریوزر) بر اساس پیام شخص غریبه"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_chat_id, user_msg_id 
            FROM message_map 
            WHERE anon_sender_id = ? AND anon_msg_id = ?
        """, (anon_sender_id, anon_msg_id)) as cursor:
            return await cursor.fetchone()  # خروجی: (user_chat_id, user_msg_id)

# ────────────────────────────────────────────────────────
# 🚫 توابع مدیریت لیست سیاه (Block List)
# ────────────────────────────────────────────────────────

async def block_user(owner_id: int, blocked_id: int):
    """بلاک کردن دائمی یک کاربر ناشناس توسط صاحب لینک"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO block_list (owner_id, blocked_id)
            VALUES (?, ?)
        """, (owner_id, blocked_id))
        await db.commit()

async def is_user_blocked(owner_id: int, blocked_id: int) -> bool:
    """بررسی اینکه آیا فرستنده ناشناس توسط صاحب لینک بلاک شده است یا خیر"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 1 FROM block_list 
            WHERE owner_id = ? AND blocked_id = ?
        """, (owner_id, blocked_id)) as cursor:
            row = await cursor.fetchone()
            return row is not None