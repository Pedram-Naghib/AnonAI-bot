import os
from datetime import datetime, timedelta
from src.ai.client import ai_client, types
from src.database.db_manager import get_daily_group_logs, clean_old_logs
from src.config import GROUP_CHAT_ID

async def send_daily_analytics(bot):
    """استخراج پیام‌های ۲۴ ساعت گذشته، رتبه‌بندی دقیق در پایتون و تولید گزارش سمی روزانه با جمینای"""
    # 📥 فراخوانی ناهمگام لاگ‌های دیتابیس اصلی
    rows = await get_daily_group_logs()
    
    if not rows:
        print("⚠️ No logs found for the last 24 hours. Analytics skipped.")
        return

    # دسته‌بندی پیام‌ها و شمارش تعداد آن‌ها در پایتون (رفع باگ عدم توانایی شمارش جمینای)
    user_chats = {}
    message_counts = {}
    
    for first_name, username, text in rows:
        user_key = f"{first_name} (@{username})" if username else first_name
        if user_key not in user_chats:
            user_chats[user_key] = []
        user_chats[user_key].append(text)
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

    # 📝 پرامپت نهایی و شخصی‌سازی شده هومبان
    analytics_instruction = """
    You are Humban, a brutally honest, highly sarcastic, and witty group analyst for a close Persian crew.
    You are given the last 24 hours of chat logs, along with an exact message count ranking calculated by the system.
    Your job is to analyze the text and generate the "Daily Group Report" (گزارش حواشی و مانیتورینگ اعضا) exactly with the following format.
    
    Requirements for the output format (Use bold informal Persian like **تیتر** for headers. Do NOT use markdown # or ### headers as Telegram doesn't render them well):
    
    1. **📊 گه خور ترین ها**: 
       List exactly top 5 users (or fewer if total active users are less than 5) based on the "EXACT RANKING" provided in the prompt. Do NOT change the order or the counts. Add a tiny sarcastic or savage comment about why they won't shut up today.
       
    2. **⌨️ کص‌دست‌ترین‌ها**: 
       Analyze the text of each user. List exactly 3 users who had the most typos, bad spelling, or incomprehensible fast-typing mistakes. Roast their typing skills heavily.
       
    3. **🤬 بیشعورترین‌ها**: 
       Analyze the vulgarity, swearing, and aggressive/rude tone of each user. List exactly 3 users who used the most profanity or street insults, ranked from most to least.
       
    4. **🔥 سوژه روز**: 
       Summarize the main funny drama, argument, or hot topic that the group discussed today in a hilarious, cinematic, and exaggerated way.
       
    5. **💬 جمله برتر روز**: 
       Quote one exact funny, stupid, or epic line from the logs, mention who said it, and roast them hard for it.

    Tone Rules: Use heavy Persian street slang (حاجی، سم، اسید، داغون، سوتون، بوی مصلحت، بگایی). Be funny, edgy, and punchy. Stay strictly within standard high-safety thresholds, but don't be a soft political correct bot. Be a roaster.
    """

    try:
        # ترکیب آمار پایتون و لاگ‌های خام برای ورودی جمینای
        full_context = f"{ranking_context}\n\nHere is the grouped chat data:\n\n{formatted_logs}"

        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_context,
            config=types.GenerateContentConfig(
                system_instruction=analytics_instruction,
                safety_settings=[
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH)
                ]
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
        if user_key not in user_chats:
            user_chats[user_key] = []
        user_chats[user_key].append(text)
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

    analytics_instruction = """
    You are Humban, a brutally honest and highly sarcastic Persian group analyst. 
    Analyze the given logs and generate a short, funny daily report with exact sections using standard Markdown:
    **📊 گه خور ترین ها**، **⌨️ کص‌دست‌ترین‌ها**، **🤬 بیشعورترین‌ها**، **🔥 سوژه روز** و **💬 جمله برتر روز**.
    Use heavy Persian street slang. Do NOT use # headers.
    """

    try:
        full_context = f"{ranking_context}\n\nHere is the test chat data:\n\n{formatted_logs}"
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_context,
            config=types.GenerateContentConfig(
                system_instruction=analytics_instruction,
                safety_settings=[
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH),
                    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH)
                ]
            )
        )
        report_text = response.text if response.text else "خطا در تولید متن تست."
        await bot.send_message(chat_id=chat_id, text=f"🧪 **[گزارش تست لایو هومبان]**\n\n{report_text}", parse_mode="Markdown")
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"❌ تست با خطا مواجه شد: {e}")