from telebot.async_telebot import AsyncTeleBot

from src.bot.handlers.private_anon import register_private_anon_handlers
from src.bot.handlers.admin_commands import register_admin_handlers
from src.bot.handlers.reactions import register_reaction_handlers

def register_bot_handlers(bot: AsyncTeleBot):
    """ثبت‌نام زنجیره‌ای با رعایت اولویت سفت و سخت کامندهای پیوی"""
    
    # اولویت سوم: دستورات ادمین و چت با AI
    register_admin_handlers(bot)
    
    # 🚨 پاتک اصلی: اولویت اول چت خصوصی، استارت و منوها است تا جایی گیر نکنند
    register_private_anon_handlers(bot)
    
    # اولویت چهارم: اموجی‌ها
    register_reaction_handlers(bot)
    
    print("💎 Modern Modular Handlers Activated with Strict Priorities.")