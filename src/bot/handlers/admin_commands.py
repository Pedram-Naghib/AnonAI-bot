import re
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardRemove
from src.config import GROUP_CHAT_ID
from src.ai.client import ai_client, types, generate_ai_response
from src.database.db_manager import get_daily_group_logs

GOD_ID = 6779908406          
SUPER_USERS = [247768888, 6779908406]

def register_admin_handlers(bot: AsyncTeleBot):

    @bot.message_handler(commands=['id'])
    async def handle_get_chat_id(message):
        try:
            await bot.reply_to(message, f"🆔 آیدی این چت/گروه: `{message.chat.id}`\n", parse_mode="Markdown")
        except Exception as e:
            print(f"❌ Error sending ID: {e}")

    @bot.message_handler(commands=['gp'])
    async def handle_send_msg_to_gp(message):
        if message.chat.id not in SUPER_USERS: return
        try:
            text = message.text.split("/gp ")
            await bot.send_message(GROUP_CHAT_ID, text[-1], reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            print(f"❌ Error sending gp message: {e}")

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

    @bot.message_handler(commands=['test_summary'])
    async def handle_test_summary(message):
        if message.chat.id not in SUPER_USERS: return
        await bot.reply_to(message, "📥 در حال استخراج چت‌ها و اتصال به جمینای...")
        await bot.send_chat_action(message.chat.id, action="typing")
        
        try:
            rows = await get_daily_group_logs()
            if not rows:
                rows = [
                    ("Pedram", "pedram_naghib", "حاجی این ربات چت ناشناس عجب چیزی شده بالاخره ران شد"),
                    ("Ali", "ali_test", "کص‌دست کدو اشتباه زدی باز که ارور ۴۰۰ داد"),
                    ("Pedram", "pedram_naghib", "خفه بابا درستش کردم مشکل از پلتفرم گوگل بود")
                ]

            user_chats, message_counts = {}, {}
            for first_name, username, text in rows:
                user_key = f"{first_name} (@{username})" if username else first_name
                user_chats.setdefault(user_key, []).append(text)
                message_counts[user_key] = message_counts.get(user_key, 0) + 1

            top_speakers = sorted(message_counts.items(), key=lambda x: x[1], reverse=True)
            
            # 👑 ساخت رنکینگ عددی و دقیق برای هدایت مدل
            ranking_context = "👑 EXACT RANKING BY MESSAGE COUNT (USE THESE NUMBERS):\n"
            for index, (user, count) in enumerate(top_speakers, 1):
                ranking_context += f"{index}. {user}: {count} messages\n"
                
            formatted_logs = "".join([f"=== USER: {u} ===\n" + "".join([f"- {m}\n" for m in ms]) + "\n" for u, ms in user_chats.items()])

            # 🧠 ارتقای پرامپت هومبان برای جاگذاری اعداد دقیق و تخمین‌های سمی
            analytics_instruction = (
                "You are Humban, a brutally honest, highly sarcastic, and witty group analyst for a close Persian crew.\n"
                "Your job is to generate the \"Daily Group Report\" with strict, funny numerical stats for EACH person.\n\n"
                "🚨 CRITICAL CONSTRAINT: Output MUST be concise, punchy, and strictly UNDER 2500 characters. Do NOT use markdown # headers.\n\n"
                "Format exactly like this (use bold informal Persian for headers):\n\n"
                "1. **📊 گه خور ترین ها (آمار دقیق چت)**:\n"
                "List top users based on the ranking data. You MUST include their exact message count.\n"
                "Example: - نام (با X تا پیام): [Savage short roast]\n\n"
                "2. **⌨️ کص‌دست‌ترین‌ها (آمار غلط املایی)**:\n"
                "Analyze spelling/typing mistakes from logs. Exaggerate or estimate a hilarious exact number of typos they made.\n"
                "Example: - نام (با Y تا کص‌دستی و غلط املایی): [One line roast]\n\n"
                "3. **🤬 بیشعورترین‌ها (شمارش فُحش‌ها)**:\n"
                "Count or creatively estimate the exact number of profanities, slangs, or rude terms they used.\n"
                "Example: - نام (با Z تا فُحش و بددهنی): [One line roast]\n\n"
                "4. **🔥 سوژه روز**:\n"
                "Summarize the main funny drama in maximum 3 sentences.\n\n"
                "5. **💬 جمله برتر روز**:\n"
                "Quote one exact funny line, name who said it, and roast them hard.\n\n"
                "Tone: Heavy Persian street slang (حاجی، سم، اسید، سوتون، بوی مصلحت). Be an absolute roaster, condensed and numbers-focused!"
            )
            
            full_context = f"{ranking_context}\n\nHere is the chat data:\n\n{formatted_logs}"
            safety_configs = [types.SafetySetting(category=c, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH) for c in [types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, types.HarmCategory.HARM_CATEGORY_HARASSMENT, types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT]]

            try:
                response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=full_context, config=types.GenerateContentConfig(system_instruction=analytics_instruction, safety_settings=safety_configs))
            except Exception:
                response = ai_client.models.generate_content(model='gemini-2.0-flash', contents=full_context, config=types.GenerateContentConfig(system_instruction=analytics_instruction, safety_settings=safety_configs))
            
            await bot.send_message(chat_id=message.chat.id, text=f"🧪 **[گزارش تست لایو هومبان]**\n\n{response.text}", parse_mode="Markdown")
        except Exception as e:
            await bot.send_message(message.chat.id, text=f"❌ تست با خطا مواجه شد: {e}")

    # چت مستقیم با AI در پیوی ادمین‌ها
    @bot.message_handler(func=lambda m: m.chat.type == "private" and m.chat.id in SUPER_USERS and m.text and not m.text.startswith('/'))
    async def handle_admin_ai_chat(message):
        await bot.send_chat_action(message.chat.id, action="typing")
        ai_reply = await generate_ai_response(message.text, is_god=(message.chat.id == GOD_ID))
        await bot.reply_to(message, ai_reply)