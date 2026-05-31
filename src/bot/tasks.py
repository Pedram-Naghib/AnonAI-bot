import sqlite3
from datetime import datetime, timedelta
from src.ai.client import ai_client, types
from src.database.db_manager import clean_old_logs
from src.config import GROUP_CHAT_ID

async def send_daily_analytics(bot):
    """استخراج پیام‌های ۲۴ ساعت گذشته و تولید گزارش سمی روزانه با جمینای"""
    conn = sqlite3.connect('group_logs.db')
    cursor = conn.cursor()
    
    one_day_ago = datetime.now() - timedelta(days=1)
    cursor.execute(
        "SELECT first_name, username, message_text FROM messages WHERE timestamp > ?", 
        (one_day_ago,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return

    user_chats = {}
    for first_name, username, text in rows:
        user_key = f"{first_name} (@{username})"
        if user_key not in user_chats:
            user_chats[user_key] = []
        user_chats[user_key].append(text)

    formatted_logs = ""
    for user, messages in user_chats.items():
        formatted_logs += f"=== USER: {user} (Total Messages: {len(messages)}) ===\n"
        for msg in messages:
            formatted_logs += f"- {msg}\n"
        formatted_logs += "\n"

    analytics_instruction = """
    You are Humban, a brutally honest, highly sarcastic, and witty group analyst for a close Persian crew.
    ... (همون پرامپت قبلی بدون تغییر) ...
    """

    try:
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Here is the grouped chat data for the last 24 hours:\n\n{formatted_logs}",
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
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=report_text, parse_mode="Markdown")
        clean_old_logs()
        
    except Exception as e:
        print(f"❌ Error in Custom Daily Analytics: {e}")