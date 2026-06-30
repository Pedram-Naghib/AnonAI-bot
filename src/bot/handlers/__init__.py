from telebot.async_telebot import AsyncTeleBot

# وارد کردن تمام هندلرهای تفکیک‌شده و ماژولار پروژه
from src.bot.handlers.admin_commands import register_admin_handlers
from src.bot.handlers.random_chat import register_random_chat_handlers
from src.bot.handlers.account_management import register_account_handlers
from src.bot.handlers.whisper import register_whisper_handlers  # 🔥 اضافه شدن هندلر نجوا
from src.bot.handlers.private_anon import register_private_anon_handlers
from src.bot.handlers.reactions import register_reaction_handlers
from src.bot.handlers.userbot_cmds import register_userbot_handlers  # 🎵 پل موزیک ویس‌چت
from src.bot.handlers.help import register_help_handlers  # 💡 دستور «کمک» در گروه

def register_bot_handlers(bot: AsyncTeleBot):
    """ثبت‌نام زنجیره‌ای با رعایت اولویت سفت و سخت کامندهای پیوی"""
    
    # اولویت اول: دستورات ادمین و کارهای مدیریتی (بالاترین اولویت برای گاد مد)
    register_admin_handlers(bot)

    # 💡 دستورِ «کمک» در گروه — راهنمای ناشناس/نجوا/موزیک برای همهٔ اعضا
    register_help_handlers(bot)

    # 🎵 پلِ موزیک: دستور «پخش» در گروه و دکمه‌های شیشه‌ای ویس‌چت
    register_userbot_handlers(bot)
    
    # اولویت دوم: موتور چت تصادفی، ثبت جنسیت، فیلترها و قطع چت زنده
    register_random_chat_handlers(bot)
    
    # اولویت سوم: مدیریت حساب، پاداش روزانه، حذف اطلاعات و ریست لیست سیاه
    register_account_handlers(bot)
    
    # 🔥 اولویت ویژه: موتور نجوای مخفی اینلاین در گروه‌ها 
    # (باید قبل از پرایوت لود شود تا کالبک‌های اختصاصی آن به درستی پردازش شوند)
    register_whisper_handlers(bot)
    
    # 🚨 اولویت چهارم: استارت اولیه، رفرال و هسته پیام ناشناس پیوی
    # (چون کال‌بک جامع دارد، باید بعد از هندلرهای اختصاصی بالا ثبت شود)
    register_private_anon_handlers(bot)
    
    # اولویت پنجم: اموجی‌ها و ریکشن‌های زنده کاربران
    register_reaction_handlers(bot)
    
    print("💎 Modern Modular Handlers Activated with Strict Priorities (Whisper Engine Added).")