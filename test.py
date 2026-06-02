import asyncio
import asyncpg
import os

# لینک اتصال مستقیم به دیتابیس Postgres سوپابیس
# مثال: postgresql://postgres.[project-id]:[password]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
DB_USER = "postgres.yismztfpjnocbeyberdj"
DB_PASS = "Pedramdb@310870"  # خواندن از لوکال یا سرور رندر
DB_HOST = "aws-1-eu-central-1.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"



async def setup_database_schema():
    print("🔄 در حال اتصال مستقیم به هسته PostgreSQL سوپابیس...")
    try:
        # اتصال به دیتابیس
        conn = await asyncpg.connect(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
        )
        
        # ۱. اجرای کوئری‌های تغییر ساختار جدول و اضافه کردن ستون‌ها
        print("⏳ در حال تزریق ستون‌های اقتصاد و چت تصادفی...")
        await conn.execute('''
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS coins BIGINT DEFAULT 10,
            ADD COLUMN IF NOT EXISTS rating FLOAT DEFAULT 5.0,
            ADD COLUMN IF NOT EXISTS rating_count INT DEFAULT 0,
            ADD COLUMN IF NOT EXISTS chat_status TEXT DEFAULT 'idle',
            ADD COLUMN IF NOT EXISTS active_partner_id BIGINT DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS queue_joined_at TIMESTAMPTZ DEFAULT NULL,
            ADD COLUMN IF NOT EXISTS last_compensation_at TIMESTAMPTZ DEFAULT NULL;
        ''')
        
        # ۲. ساخت ایندکس برای افزایش سرعت سرچ در صف انتظار
        print("⚡ در حال ساخت ایندکس‌های سرعتی (Matchmaking)...")
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_chat_status_rating 
            ON users (chat_status, rating DESC);
        ''')
        
        print("✅ ساختار دیتابیس با موفقیت آپدیت شد ستون! همه چیز برای چت تصادفی آماده است.")
        await conn.close()
        
    except Exception as e:
        print(f"❌ خطا در آپدیت دیتابیس: {e}")

if __name__ == '__main__':
    asyncio.run(setup_database_schema())