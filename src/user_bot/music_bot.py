import os
from telethon import TelegramClient, events
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream  # <--- تغییر اول: استفاده از MediaStream به جای AudioPiped

# خواندن لیست سوپریوزرها از محیط
super_users_raw = os.environ.get('SUPER_USERS', '8627765327,6779908406')
SUPER_USERS = [int(user_id.strip()) for user_id in super_users_raw.split(',') if user_id.strip()]

# تشخیص محیط رندر
IS_ON_RENDER = os.environ.get('RENDER') == 'true'

if IS_ON_RENDER:
    PROXY = None
    print("🌍 در حال اجرا روی سرور رندر (بدون نیاز به پروکسی)")
else:
    import socks
    PROXY = (socks.SOCKS5, '127.0.0.1', 10808)
    print("💻 در حال اجرا روی اوبونتو داخلی (پروکسی فعال)")

api_id = os.environ.get(2410696)
api_hash = os.environ.get("7d59d477fa535d957f3650c7b1578bdd")

client = TelegramClient("music_userbot", api_id, api_hash, proxy=PROXY)
app = PyTgCalls(client)

@client.on(events.NewMessage(pattern=r'\.ping'))
async def ping_handler(event):
    if not (event.out or event.sender_id in SUPER_USERS):
        return
    await event.reply('✅ ربات بیداره و داره مثل ساعت کار می‌کنه! 😎')

@client.on(events.NewMessage(pattern=r'\.play'))
async def play_handler(event):
    if not (event.out or event.sender_id in SUPER_USERS):
        return
        
    chat_id = event.chat_id
    test_audio_url = 'http://stream.radioreklama.bg/radio1128'
    
    await event.reply('🎵 در حال اتصال به ویس‌چت و پردازش موزیک...')
    
    try:
        # تغییر دوم: استفاده از MediaStream برای پخش
        await app.play(
            chat_id,
            MediaStream(test_audio_url)
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
    await client.run_until_disconnected()

if __name__ == '__main__':
    client.loop.run_until_complete(main())