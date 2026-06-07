from telebot.async_telebot import AsyncTeleBot

# وارد کردن تمام هندلرهای تفکیک‌شده و ماژولار پروژه
from src.bot.handlers.admin_commands import register_admin_handlers
from src.bot.handlers.private_anon import register_private_anon_handlers
from src.bot.handlers.random_chat import register_random_chat_handlers
from src.bot.handlers.account_management import register_account_handlers
from src.bot.handlers.reactions import register_reaction_handlers

def register_bot_handlers(bot: AsyncTeleBot):
    """ثبت‌نام زنجیره‌ای با رعایت اولویت سفت و سخت کامندهای پیوی"""
    
    # اولویت اول: دستورات ادمین و کارهای مدیریتی (بالاترین اولویت برای گاد مد)
    register_admin_handlers(bot)
    
    # 🚨 پاتک اصلی اولویت دوم: استارت اولیه، رفرال و هسته پیام ناشناس پیوی
    register_private_anon_handlers(bot)
    
    # اولویت سوم: موتور چت تصادفی، ثبت جنسیت، فیلترها و قطع چت زنده
    register_random_chat_handlers(bot)
    
    # اولویت چهارم: مدیریت حساب، پاداش روزانه، حذف اطلاعات و ریست لیست سیاه
    register_account_handlers(bot)
    
    # اولویت پنجم: اموجی‌ها و ریکشن‌های زنده کاربران
    register_reaction_handlers(bot)
    
    print("💎 Modern Modular Handlers Activated with Strict Priorities.")