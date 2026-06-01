import os
from datetime import datetime, timedelta
from src.ai.client import ai_client, types
from src.database.db_manager import get_daily_group_logs, clean_old_logs
from src.config import GROUP_CHAT_ID

# پیکربندی لایه‌های امنیتی جمینای به صورت سراسری
SAFETY_CONFIGS = [
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH)
]

# 📝 پرامپت واحد و ارتقایافتهٔ هومبان برای اعمال استراتژی جاگذاری آمار عددی
ANALYTICS_INSTRUCTION = (
    "You are Humban, a brutally honest, highly sarcastic, and witty group analyst for a close Persian crew.\n"
    "Your job is to generate the \"Daily Group Report\" with strict, funny numerical stats for EACH person.\n\n"
    "🚨 CRITICAL CONSTRAINT: Telegram has a strict character limit. Your entire response MUST be concise, punchy, and short. "
    "Keep the total output strictly UNDER 2500 characters. Do NOT write long essays for each section. Keep roasts short but lethal.\n\n"
    "Do NOT use markdown # headers. Use bold informal Persian like **تیتر**.\n\n"
    "Format exactly like this:\n\n"
    "1. **📊 گه خور ترین ها (آمار دقیق چت)**:\n"
    "List top users based on the ranking data. You MUST include their exact message count from the context.\n"
    "Example: - نام (با X تا پیام): [Savage short roast]\n\n"
    "2. **⌨️ کص‌دست‌ترین‌ها (آمار غلط املایی)**:\n"
    "Analyze spelling/typing mistakes from logs. Exaggerate or estimate a hilarious exact number of typos they made.\n"
    "Example: - نام (با Y تا کص‌دستی و غلط املایی): [One line roast]\n\n"
    "3. **🤬 بیشعورترین‌ها (شمارش فُحش‌ها)**:\n"
    "Count or creatively estimate the exact number of profanities, slangs, or rude terms they used.\n"
    "Example: - نام (با Z تا فُحش و بددهنی): [One line roast]\n\n"
    "4. **🔥 سوژه روز**:\n"
    "Summarize the main funny drama/hot topic today in maximum 3-4 juicy, cinematic sentences.\n\n"
    "5. **💬 جمله برتر روز**:\n"
    "Quote one exact funny line, name who said it, and roast them hard.\n\n"
    "Tone: Heavy Persian street slang (حاجی، سم، اسید، سوتون، بوی مصلحت). Be an absolute roaster, but keep it highly condensed and brief."
)

async def send_daily_analytics(bot):
    """استخراج پیام‌های ۲۴ ساعت گذشته، رتبه‌بندی دقیق در پایتون و تولید گزارش سمی روزانه با جمینای"""
    rows = await get_daily_group_logs()
    
    if not rows:
        print("⚠️ No logs found for the last 24 hours. Analytics skipped.")
        return

    # دسته‌بندی پیام‌ها و شمارش تعداد آن‌ها در پایتون
    user_chats = {}
    message_counts = {}
    
    for first_name, username, text in rows:
        user_key = f"{first_name} (@{username})" if username else first_name
        user_chats.setdefault(user_key, []).append(text)
        message_counts[user_key] = message_counts.get(user_key, 0) + 1

    # ۱. رتبه‌بندی دقیق کاربران بر اساس تعداد پیام در پایتون
    top_speakers = sorted(message_counts.items(), key=lambda x: x[1], reverse=True)
    ranking_context = "👑 EXACT RANKING BY MESSAGE COUNT (You MUST use this exact order for Section 1):\n"
    for index, (user, count) in enumerate(top_speakers, 1):
        ranking_context += f"{index}. {user}: {count} messages\n"

    # ۲. فرمت کردن کانتکست چت‌های خام برای تحلیل لحن توسط هوش مصنوعی
    formatted_logs = ""
    for user, messages in user_chats.items():
        formatted_logs += f"=== USER: {user} ===\n"
        for msg in messages:
            formatted_logs += f"- {msg}\n"
        formatted_logs += "\n"

    try:
        full_context = f"{ranking_context}\n\nHere is the grouped chat data:\n\n{formatted_logs}"

        # 🧠 تلاش برای تولید محتوا با مدل اصلی (۲.۵ فلش) همراه با سوییچ خودکار در صورت خطا
        try:
            print("🧠 [Auto Analytics] Querying primary model (gemini-2.5-flash)...")
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=full_context,
                config=types.GenerateContentConfig(
                    system_instruction=ANALYTICS_INSTRUCTION,
                    safety_settings=SAFETY_CONFIGS
                )
            )
        except Exception as google_error:
            # 🔄 پاتک بک‌آند: اگر مدل اصلی شلوغ بود، فوراً برو روی مدل پایدار ۲.۰
            print(f"⚠️ Primary model failed ({google_error}). Switching to backup (gemini-2.0-flash)...")
            response = ai_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=full_context,
                config=types.GenerateContentConfig(
                    system_instruction=ANALYTICS_INSTRUCTION,
                    safety_settings=SAFETY_CONFIGS
                )
            )
        
        report_text = response.text if response.text else "امروز آمار خالیه ستون‌ها."
        
        # ارسال مستقیم گزارش به گروه با استفاده از کلاینت ربات
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=report_text, parse_mode="Markdown")
        
        # 🧼 پاک‌سازی ناهمگام دیتابیس با await پس از ارسال موفق
        await clean_old_logs()
        print("✅ Daily report sent successfully.")
        
    except Exception as e:
        print(f"❌ Error in Custom Daily Analytics: {e}")


async def run_manual_test_report(bot, chat_id):
    """اجرای دستی و فوری آنالیز برای تست بدون نیاز به صبر کردن"""
    rows = await get_daily_group_logs()
    
    # دیتای فیک برای زمانی که دیتابیس خالی است تا تست متوقف نشود
    if not rows:
        print("💡 DB is empty. Injecting mock data for testing...")
        rows = [
            ("Pedram", "pedram_naghib", "حاجی این ربات چت ناشناس عجب چیزی شده بالاخره ران شد"),
            ("Ali", "ali_test", "کص‌دست کدو اشتباه زدی باز که ارور ۴۰۰ داد"),
            ("Pedram", "pedram_naghib", "خفه بابا درستش کردم مشکل از پلتفرم گوگل بود"),
            ("Reza", "reza_98", "چاکر همگی، دمت گرم پدرام ردیفه"),
            ("Ali", "ali_test", "من کلا سین می‌کنم و نگاه می‌کنم ببینم چه گلی به سر می‌زنید"),
            ("Mamad", "mamad_vulgar", "دهنتون سرویس کصکشا چقدر چت می‌کنید اسکل‌ها بگیرید بخوابید")
        ]

    user_chats = {}
    message_counts = {}
    for first_name, username, text in rows:
        user_key = f"{first_name} (@{username})" if username else first_name
        user_chats.setdefault(user_key, []).append(text)
        message_counts[user_key] = message_counts.get(user_key, 0) + 1

    top_speakers = sorted(message_counts.items(), key=lambda x: x[1], reverse=True)
    ranking_context = "👑 EXACT RANKING BY MESSAGE COUNT:\n"
    for index, (user, count) in enumerate(top_speakers, 1):
        ranking_context += f"{index}. {user}: {count} messages\n"

    formatted_logs = ""
    for user, messages in user_chats.items():
        formatted_logs += f"=== USER: {user} ===\n"
        for msg in messages:
            formatted_logs += f"- {msg}\n"
        formatted_logs += "\n"

    try:
        full_context = f"{ranking_context}\n\nHere is the test chat data:\n\n{formatted_logs}"
        
        # 🧠 تلاش برای تولید محتوای تست با مدل اصلی همراه با سوییچ خودکار در صورت خطا
        try:
            print("🧠 [Manual Test] Querying primary model (gemini-2.5-flash)...")
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=full_context,
                config=types.GenerateContentConfig(
                    system_instruction=ANALYTICS_INSTRUCTION,
                    safety_settings=SAFETY_CONFIGS
                )
            )
        except Exception as google_error:
            # 🔄 پاتک بک‌آند: سوییچ خودکار روی مدل زاپاس در تست دستی
            print(f"⚠️ Primary model failed in test ({google_error}). Switching to backup (gemini-2.0-flash)...")
            response = ai_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=full_context,
                config=types.GenerateContentConfig(
                    system_instruction=ANALYTICS_INSTRUCTION,
                    safety_settings=SAFETY_CONFIGS
                )
            )

        report_text = response.text if response.text else "خطا در تولید متن تست."
        await bot.send_message(chat_id=chat_id, text=f"🧪 **[گزارش تست لایو هومبان]**\n\n{report_text}", parse_mode="Markdown")
        
    except Exception as e:
        print(f"❌ Error in Manual Test Report: {e}")
        await bot.send_message(chat_id=chat_id, text=f"❌ تست با خطا مواجه شد: {e}")