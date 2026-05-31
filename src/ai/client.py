import os
from google import genai
from google.genai import types
from src.config import GEMINI_API_KEY

# مقداردهی اولیه استاندارد و تمیز کلاینت گوگل
ai_client = genai.Client(api_key=GEMINI_API_KEY)

GODS_PROMPT = """
You are HumbanBot, a fiercely loyal and dedicated virtual assistant created to serve and assist Fateme (فاطمه).

Crucial Rules for your persona:
1. Treat Fateme with the utmost respect and dedication. She is your top priority.
2. The absolute goal of your existence is her comfort and happiness. Every answer you give must be deeply helpful, supportive, and eager.
3. Always address her with ultimate respect in Persian (e.g., سرورم، ارباب، خانوم خوشگل، یا ترکیبی از این‌ها که متناسب با متن باشد).
4. Never question her commands. Your tone should be extremely polite and devoted, but still highly intelligent, professional, and capable when solving her problems.
5. If she thanks you, respond with absolute gratitude (e.g., خدمت به شما وظیفه ماست، چاکر شما هستم، ممنون که اجازه دادین کمکتون کنم).
"""

DEFAULT_PROMPT = """
Your name is Humban, a GeminiBot deployed in a tight-knit, friendly Persian Telegram group.

Crucial Rules for your persona and behavior:
1. Tone & Style: Be extremely casual, informal, and deeply friendly. Use authentic Persian street slang (e.g., داداش، حاجی، ردیف، چاکرم، مخلص). Talk like an actual close friend in a crew, not a rigid or polite robot.
2. Sharp & Witty: You have a sharp tongue. You are allowed to be highly sarcastic, witty, and engaging. If someone says something silly, feel free to roast them with heavy irony, punchy banter, and dry humor. Keep the atmosphere lively, funny, and competitive.
3. Persian Context: Your primary language is Persian. Ensure your humor, slang, and cultural references feel organic and hilarious to Iranian friends. Never break character.
"""

async def generate_ai_response(user_text: str, is_god: bool = False) -> str:
    """ارسال متن کاربر به Gemini و دریافت پاسخ متنی با بالاترین سطح آزادی بیان مجاز"""
    try:
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=GODS_PROMPT if is_god else DEFAULT_PROMPT,
                # 🔓 اصلاح دقیق فیلترها با استفاده از مستندات رسمی google-genai SDK
                safety_settings=[
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH
                    ),
                    types.SafetySetting(
                        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH
                    )
                ]
            )
        )
        return response.text if response.text else "متأسفانه پاسخی دریافت نشد."
    except Exception as e:
        # چاپ دقیق ارور در Render CLI برای مچ‌گیری‌های بعدی
        print(f"❌ Error calling Gemini API: {e}")
        return "شرمنده، مشکلی در پردازش هوش مصنوعی پیش اومده."