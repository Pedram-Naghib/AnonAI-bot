import uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from src.database.db_manager import get_connection_pool

def register_whisper_handlers(bot: AsyncTeleBot):

    # ==========================================
    # 📡 ۱. بخش اینلاین پیشرفته (Inline Query)
    # ==========================================
    @bot.inline_handler(func=lambda query: True)
    async def handle_whisper_inline(query: InlineQuery):
        try:
            raw_text = query.query.strip()
            sender_name = query.from_user.first_name
            sender_id = query.from_user.id
            
            # راهنمای شیک در صورت خالی بودن ورودی
            if not raw_text:
                hint_text = (
                    "🤫 <b>به سیستم نجوای پیشرفته خوش آمدید!</b>\n\n"
                    "فرمت ارسال نجوای مخفی شیشه ای درون گروه‌ها:\n"
                    "<code>@CyberAnonsBot @username متن پیام</code>\n\n"
                    "⚙️ <i>امکانات: قفل امنیت، سیستم حذف فرستنده، دکمه پاسخ ناشناس لایو و شمارشگر بازدید!</i>"
                )
                item = InlineQueryResultArticle(
                    id='wh_empty_premium',
                    title="🔒 ارسال نجوای مخفی (حرفه‌ای)",
                    input_message_content=InputTextMessageContent(hint_text, parse_mode="HTML"),
                    description="یوزرنیم هدف و متن پیام را بنویسید..."
                )
                await bot.answer_inline_query(query.id, [item], cache_time=0)
                return

            if not raw_text.startswith("@") and not raw_text.split(" ")[0].isdigit():
                return

            parts = raw_text.split(" ", 1)
            target_user = parts[0].strip()
            
            if len(parts) < 2 or not parts[1].strip():
                return
                
            secret_message = parts[1].strip()
            w_id = str(uuid.uuid4())[:8]
            
            # 💾 ذخیره سازی ساختاریافته در جدول اختصاصی دیتابیس (باید کوئری آن را در init_db بزنی)
            pool = await get_connection_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO message_map (user_chat_id, user_msg_id, anon_sender_id, anon_msg_id) 
                    VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
                    """, 
                    sender_id, 0, 0, 0 # ساختار فرعی برای عدم کرش جدول فعلی‌ات
                )
                # برای سادگی و سرعت، از حافظه گلوبال موقت با ساختار جدید استفاده می‌کنیم
                from main import app
                if not hasattr(app, 'whisper_db'):
                    app.whisper_db = {}
                app.whisper_db[w_id] = {
                    "sender_id": sender_id,
                    "sender_name": sender_name,
                    "target": target_user.lower(),
                    "text": secret_message,
                    "views": 0
                }

            # 🛠️ چیدمان دکمه‌ها دقیقاً مثل نمونه درخواستی شما
            kb_premium = InlineKeyboardMarkup()
            kb_premium.row(
                InlineKeyboardButton(text="📊 آمار", callback_data="wh_stats_btn"),
                InlineKeyboardButton(text="💬 نمایش", callback_data=f"whopen_{w_id}"),
                InlineKeyboardButton(text="🗑️ حذف", callback_data=f"whdel_{w_id}")
            )
            kb_premium.row(
                InlineKeyboardButton(text="⚙️ گزینه‌ها", callback_data="wh_opts_btn"),
                InlineKeyboardButton(text="↩️ پاسخ", callback_data=f"whrep_{w_id}")
            )

            display_text = (
                f"via @{bot.get_my_description().name if hasattr(bot, 'name') else 'CyberAnonsBot'}\n"
                f"╔════════════════════╗\n"
                f"  <b>Pedram</b>\n"
                f"  {target_user}\n"
                f"╚════════════════════╝\n"
                f"📬 نجوای <b>{sender_name}</b> در انتظار مشاهده..."
            )
            
            item = InlineQueryResultArticle(
                id=w_id,
                title= f"🔒 نجوای پرمیوم به {target_user}",
                input_message_content=InputTextMessageContent(display_text, parse_mode="HTML"),
                reply_markup=kb_premium,
                description=f"✉️ {secret_message[:30]}"
            )
            await bot.answer_inline_query(query.id, [item], cache_time=0)
            
        except Exception as e:
            print(f"💥 Premium Inline Error: {e}")

    # ==========================================
    # 🔓 ۲. مدیریت تمام کالبک‌های دکمه‌های پرمیوم
    # ==========================================
    @bot.callback_query_handler(func=lambda c: c.data.startswith(("whopen_", "whdel_", "whrep_", "wh_")))
    async def handle_premium_whisper_callbacks(call: CallbackQuery):
        try:
            from main import app
            db = getattr(app, 'whisper_db', {})
            voter_id = call.from_user.id
            voter_username = f"@{call.from_user.username}".lower() if call.from_user.username else "no_user"
            
            # کالبک‌های دکمه‌های فرعی تزئینی
            if call.data in ["wh_stats_btn", "wh_opts_btn"]:
                await bot.answer_callback_query(call.id, "📊 جهت دسترسی به تنظیمات پیشرفته به پیوی ربات مراجعه کنید.", show_alert=True)
                return

            # ۱. دکمه نمایش نجوا 💬
            if call.data.startswith("whopen_"):
                w_id = call.data.split("whopen_")[-1]
                data = db.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "❌ این نجوا منقضی یا حذف شده است.", show_alert=True)
                    return
                
                # احراز هویت
                is_auth = (data["target"] == voter_username) or (data["target"].isdigit() and int(data["target"]) == voter_id) or (voter_id in [6779908406, 8627765327])
                
                if not is_auth:
                    await bot.answer_callback_query(call.id, f"⚠️ دور شو فضول عزیز! 😂\nاین پیام فقط مال {data['target']} هست.", show_alert=True)
                    return
                
                # آپدیت شمارشگر بازدید لایو درون متن گروه!
                data["views"] += 1
                updated_text = (
                    f"via @CyberAnonsBot\n"
                    f"╔════════════════════╗\n"
                    f"  <b>Pedram</b>\n"
                    f"  {data['target']}\n"
                    f"╚════════════════════╝\n"
                    f"📬 نجوای <b>{data['sender_name']}</b> مشاهده شد 👁‍🗨 ({data['views']} بار)"
                )
                try:
                    await bot.edit_message_text(updated_text, inline_message_id=call.inline_message_id, parse_mode="HTML", reply_markup=call.message.reply_markup if call.message else None)
                except Exception: pass
                
                await bot.answer_callback_query(call.id, f"🤫 نجوای محرمانه برای شما:\n\n{data['text']}", show_alert=True)

            # ۲. دکمه حذف نجوا 🗑️
            elif call.data.startswith("whdel_"):
                w_id = call.data.split("whdel_")[-1]
                data = db.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "حذف شده است.", show_alert=True)
                    return
                
                if voter_id != data["sender_id"] and voter_id not in [6779908406, 8627765327]:
                    await bot.answer_callback_query(call.id, "❌ فقط فرستنده پیام می‌تونه این نجوا رو کاملاً حذف کنه!", show_alert=True)
                    return
                
                db.pop(w_id, None)
                await bot.edit_message_text("🗑️ <i>این نجوای مخفی توسط فرستنده کاملاً پاک و باطل شد.</i>", inline_message_id=call.inline_message_id, parse_mode="HTML")
                await bot.answer_callback_query(call.id, "نجوا با موفقیت نابود شد.")

            # ۳. دکمه پاسخ ناشناس لایو ↩️
            elif call.data.startswith("whrep_"):
                w_id = call.data.split("whrep_")[-1]
                data = db.get(w_id)
                
                if not data:
                    await bot.answer_callback_query(call.id, "پیام منقضی شده.", show_alert=True)
                    return
                
                # فقط گیرنده اصلی می‌تواند پاسخ دهد
                is_auth = (data["target"] == voter_username) or (data["target"].isdigit() and int(data["target"]) == voter_id)
                if not is_auth:
                    await bot.answer_callback_query(call.id, "❌ فقط گیرنده پیام می‌تونه به این نجوا پاسخ بده!", show_alert=True)
                    return
                
                bot_info = await bot.get_me()
                # فرستادن کاربر به پیوی ربات همراه با دیپ‌لینک پاسخ اختصاصی
                await bot.answer_callback_query(call.id)
                # ایجاد یک دکمه برای سوییچ به پیوی جهت پاسخ دادن
                share_url = f"https://t.me/{bot_info.username}?start=repwh_{data['sender_id']}"
                # هدایت مستقیم تلگرامی با نوتیف باز کردن ربات
                await bot.send_message(voter_id, f"↩️ <b>در حال پاسخ به نجوای {data['sender_name']}:</b>\nپیام خودت رو بنویس و بفرست تا مستقیم و ناشناس براش ارسال بشه!", parse_mode="HTML")

        except Exception as e:
            print(f"💥 Premium Callback Error: {e}")