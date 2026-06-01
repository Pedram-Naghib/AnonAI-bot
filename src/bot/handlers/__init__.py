from telebot.async_telebot import AsyncTeleBot

# 📥 ایمپورت کردن ثبت‌نام کننده‌های هر لایه به صورت ماژولار
from .group_monitor import register_group_handlers
from .admin_commands import register_admin_handlers
from .private_anon import register_private_anon_handlers
from .reactions import register_reaction_handlers

def register_bot_handlers(bot: AsyncTeleBot):
    """ثبت‌نام مرکزی و سلسله‌مراتبی هندلرهای ربات هومبان بر اساس ارجحیت رویدادها"""
    
    # ۱. اولویت اول: بررسی پیام‌های ارسالی در گروه اصلی (قفل مانیتورینگ)
    register_group_handlers(bot)
    
    # ۲. اولویت دوم: دستورات ارشد و ارتباط با جمینای
    register_admin_handlers(bot)
    
    # ۳. اولویت سوم: سناریوی پینگ‌پنگی چت ناشناس پیوی و FSM
    register_private_anon_handlers(bot)
    
    # ۴. اولویت چهارم: هندل لایو ری‌آکشن‌های تلگرام
    register_reaction_handlers(bot)
    
    print("💎 Architecture Upgrade: All modern handlers sub-modules synchronized successfully.")