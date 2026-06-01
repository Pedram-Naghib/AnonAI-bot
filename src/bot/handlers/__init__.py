from telebot.async_telebot import AsyncTeleBot

# 🚀 استفاده از ایمپورت مطلق (Absolute Import) برای حل مشکل رندر
from src.bot.handlers.group_monitor import register_group_handlers
from src.bot.handlers.admin_commands import register_admin_handlers
from src.bot.handlers.private_anon import register_private_anon_handlers
from src.bot.handlers.reactions import register_reaction_handlers

def register_bot_handlers(bot: AsyncTeleBot):
    """ثبت‌نام مرکزی و سلسله‌مراتبی هندلرهای ربات هومبان"""
    
    # ۱. مانیتورینگ گروه اصلی
    register_group_handlers(bot)
    
    # ۲. دستورات ارشد و ارتباط با جمینای
    register_admin_handlers(bot)
    
    # ۳. سناریوی چت ناشناس پیوی
    register_private_anon_handlers(bot)
    
    # ۴. هندل لایو ری‌آکشن‌ها
    register_reaction_handlers(bot)
    
    print("💎 Architecture Upgrade: All modern handlers sub-modules synchronized successfully.")