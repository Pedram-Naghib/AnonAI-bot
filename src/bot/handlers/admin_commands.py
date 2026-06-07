import re
import traceback
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardRemove

# وارد کردن تنظیمات و توابع پایه مورد نیاز
from src.config import GROUP_CHAT_ID
from src.database.db_manager import get_connection_pool

GOD_ID = 6779908406          
SUPER_USERS = [8627765327, 6779908406]

def register_admin_handlers(bot: AsyncTeleBot):

    # ==========================================
    # ⚙️ دستور دریافت آیدی چت یا گروه
    # ==========================================
    @bot.message_handler(commands=['id'])
    async def handle_get_chat_id(message):
        try:
            await bot.reply_to(message, f"🆔 آیدی این چت/گروه: `{message.chat.id}`\n", parse_mode="Markdown")
        except Exception as e:
            print(f"❌ Error sending ID: {e}")

    # ==========================================
    # ⚙️ دستور ارسال پیام مستقیم به گروه از طریق ربات
    # ==========================================
    @bot.message_handler(commands=['gp'])
    async def handle_send_msg_to_gp(message):
        if message.chat.id not in SUPER_USERS: return
        try:
            text = message.text.split("/gp ")
            await bot.send_message(GROUP_CHAT_ID, text[-1], reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            print(f"❌ Error sending gp message: {e}")

    # ==========================================
    # ⚙️ دستور ریپلای خودکار روی لینک‌های پرایوت گروه
    # ==========================================
    @bot.message_handler(regexp=r"^https:\/\/t\.me\/c\/1434396268\/(\d+)\s+(.*)")
    async def handle_auto_reply_by_link(message):
        if message.chat.id not in SUPER_USERS: return
        try:
            match = re.match(r"^https:\/\/t\.me\/c\/1434396268\/(\d+)\s+(.*)", message.text)
            if match:
                reply_to_msg_id = int(match.group(1))
                clean_text = match.group(2)
                await bot.send_message(GROUP_CHAT_ID, text=clean_text, reply_to_message_id=reply_to_msg_id, reply_markup=ReplyKeyboardRemove())
                await bot.reply_to(message, f"🎯 روی پیام `{reply_to_msg_id}` ریپلای شد!")
        except Exception as e:
            print(f"❌ Error in link auto-reply: {e}")

    # ==========================================
    # 👑 دستور ویژه مدیریت: دریافت آمار پیشرفته دیتابیس کاربران فعال
    # ==========================================
    @bot.message_handler(commands=['db_stats'], func=lambda m: m.chat.type == "private" and m.from_user.id in SUPER_USERS)
    async def handle_god_db_stats(message):
        # ارسال چت اکشن تایپینگ برای ادمین جهت تایید دریافت دستور
        await bot.send_chat_action(GOD_ID, 'typing')
        
        pool = await get_connection_pool()
        
        try:
            async with pool.acquire() as conn:
                # کوئری ترکیبی برای محاسبه تعداد ارسال و دریافت هر کاربر بر اساس جدول نگاشت پیام‌ها
                query = """
                    SELECT 
                        u.user_id, 
                        u.first_name, 
                        u.username,
                        COALESCE(r.received_count, 0) AS received,
                        COALESCE(s.sent_count, 0) AS sent
                    FROM users u
                    LEFT JOIN (
                        SELECT user_chat_id, COUNT(*) AS received_count 
                        FROM message_map 
                        GROUP BY user_chat_id
                    ) r ON u.user_id = r.user_chat_id
                    LEFT JOIN (
                        SELECT anon_sender_id, COUNT(*) AS sent_count 
                        FROM message_map 
                        GROUP BY anon_sender_id
                    ) s ON u.user_id = s.anon_sender_id
                    ORDER BY (COALESCE(r.received_count, 0) + COALESCE(s.sent_count, 0)) DESC
                    LIMIT 20; -- نمایش ۲۰ کاربر فعال‌تر اول جهت جلوگیری از طولانی شدن متن پیام
                """
                
                rows = await conn.fetch(query)
                
                if not rows:
                    await bot.reply_to(message, "📭 هیچ کاربری در دیتابیس یافت نشد.")
                    return
                
                report_lines = [
                    "👑 <b>گزارش ارشد دیتابیس کاربران فعال</b>\n",
                    "📊 <i>۲۰ کاربر برتر بر اساس بیشترین حجم تعاملات ناشناس:</i>\n"
                ]
                
                for index, row in enumerate(rows, 1):
                    uid = row['user_id']
                    name = row['first_name'] or "Unknown"
                    username = f"@{row['username']}" if row['username'] else "بدون یوزرنیم"
                    received = row['received']
                    sent = row['sent']
                    
                    # بررسی زنده وضعیت بلاک (فقط کاربرانی که ربات را بلاک نکرده‌اند)
                    try:
                        await bot.send_chat_action(uid, 'typing')
                    except Exception:
                        # کاربر ربات را بلاک کرده است؛ نادیده گرفته می‌شود
                        continue
                    
                    line = (
                        f"{index}. 👤 <b>{name}</b> (<code>{uid}</code>) | {username}\n"
                        f"   📥 دریافتی: <b>{received}</b> | 📤 ارسالی: <b>{sent}</b>\n"
                        f"   ➖"
                    )
                    report_lines.append(line)
                
                # بررسی اینکه آیا کاربری بعد از فیلتر بلاکی‌ها باقی مانده است یا خیر
                if len(report_lines) == 2:
                    await bot.reply_to(message, "⚠️ تمام کاربران موجود در این بخش، ربات را مسدود (Block) کرده‌اند.")
                    return
                    
                final_report = "\n".join(report_lines)
                await bot.reply_to(message, final_report, parse_mode="HTML")
                
        except Exception as err:
            print(f"💥 Admin Stats Command Failed: {err}")
            traceback.print_exc()
            await bot.reply_to(message, "❌ خطایی در استخراج اطلاعات از دیتابیس رخ داد.")