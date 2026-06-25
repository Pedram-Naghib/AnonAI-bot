import os
from telethon import TelegramClient, events
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped

# خواندن لیست سوپریوزرها از محیط (اگر پیدا نکرد، همون لیست دستی رو پیش‌فرض می‌ذاره)
super_users_raw = os.environ.get('SUPER_USERS', '8627765327,6779908406')
# تبدیل رشته متنی به یک لیست از اعداد (Integer)
SUPER_USERS = [int(user_id.strip()) for user_id in super_users_raw.split(',') if user_id.strip()]

# بررسی می‌کنیم آیا اسکریپت روی سرور رندر در حال اجراست یا سیستم شخصی
IS_ON_RENDER = os.environ.get('RENDER') == 'true'

if IS_ON_RENDER:
    PROXY = None
    print("🌍 در حال اجرا روی سرور رندر (بدون نیاز به پروکسی)")
else:
    import socks
    PROXY = (socks.SOCKS5, '127.0.0.1', 10808)
    print("💻 در حال اجرا روی اوبونتو داخلی (پروکسی فعال)")

api_id = 2410696
api_hash = '7d59d477fa535d957f3650c7b1578bdd'

# کلاینت یوزربات با تنظیماتِ هوشمندِ پروکسی
client = TelegramClient("music_userbot", api_id, api_hash, proxy=PROXY)

# راه‌اندازی موتور پخش صدا (pytgcalls) روی کلاینت تله‌تون
app = PyTgCalls(client)

# هندلر برای تست زنده بودن یوزربات
@client.on(events.NewMessage(pattern=r'\.ping'))
async def ping_handler(event):
    # قفل امنیتی: بررسی دسترسی سوپریوزر
    if not (event.out or event.sender_id in SUPER_USERS):
        return
        
    await event.reply('✅ ربات بیداره و داره مثل ساعت کار می‌کنه! 😎')

# هندلر برای پخش موزیک
@client.on(events.NewMessage(pattern=r'\.play'))
async def play_handler(event):
    # قفل امنیتی: بررسی دسترسی سوپریوزر
    if not (event.out or event.sender_id in SUPER_USERS):
        return
        
    chat_id = event.chat_id
    
    # یک لینک موزیک یا مسیر فایل محلی برای تست
    test_audio_url = 'http://stream.radioreklama.bg/radio1128'
    
    await event.reply('🎵 در حال اتصال به ویس‌چت و پردازش موزیک...')
    
    try:
        # اجرای موزیک در ویس‌چتِ همون گروهی که دستور رو دادی
        await app.play(
            chat_id,
            AudioPiped(test_audio_url)
        )
        await event.reply('▶️ پخش با موفقیت شروع شد!')
    except Exception as e:
        await event.reply(f'❌ ارور در پخش (مطمئن شو ویس‌چت گروه روشنه!):\n`{e}`')

async def main():
    print("🚀 در حال استارت موتور Telethon...")
    await client.start()
    print("🎧 در حال استارت موتور PyTgCalls...")
    await app.start()
    print(f"✅ سیستم کاملاً آماده است! سوپریوزرها: {SUPER_USERS}")
    
    # روشن نگه داشتن ربات
    await client.run_until_disconnected()

if __name__ == '__main__':
    client.loop.run_until_complete(main())