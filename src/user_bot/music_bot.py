import os
from telethon import TelegramClient, events
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

# 🔥 فعال‌سازی FFmpeg برای رفع مشکل صدا در سرور رندر
from static_ffmpeg import add_paths
add_paths()

# خواندن لیست سوپریوزرها از محیط
super_users_raw = os.environ.get('SUPER_USERS', '8627765327,6779908406')
SUPER_USERS = [int(user_id.strip()) for user_id in super_users_raw.split(',') if user_id.strip()]

# خواندن آیدی گروه اختصاصی (اگر تو env نبود، None در نظر می‌گیره)
group_chat_id_raw = os.environ.get('GROUP_CHAT_ID')
GROUP_CHAT_ID = int(group_chat_id_raw.strip()) if group_chat_id_raw else None

# تشخیص محیط رندر
IS_ON_RENDER = os.environ.get('RENDER') == 'true'

if IS_ON_RENDER:
    PROXY = None
    print("🌍 در حال اجرا روی سرور رندر (بدون نیاز به پروکسی)")
else:
    import socks
    PROXY = (socks.SOCKS5, '127.0.0.1', 10808)
    print("💻 در حال اجرا روی اوبونتو داخلی (پروکسی فعال)")

# تبدیل متغیرهای محیطی به فرمت درست
api_id = int(os.environ.get("API_ID", 2410696))
api_hash = os.environ.get("API_HASH", "7d59d477fa535d957f3650c7b1578bdd")

client = TelegramClient("music_userbot", api_id, api_hash, proxy=PROXY)
app = PyTgCalls(client)


# ── هندلر پینگ ─────────────────────────────────────────
@client.on(events.NewMessage(pattern=r'\.ping'))
async def ping_handler(event):
    if not (event.out or event.sender_id in SUPER_USERS or event.chat_id == GROUP_CHAT_ID):
        return
    await event.reply('✅ رباتِ دی‌جی بیداره و داره مثل ساعت کار می‌کنه! 😎')


# ── هندلر پخش آهنگ (فارسی و انگلیسی) ──────────────────────
# با تایپ کردن .play یا کلمه "پخش" فعال می‌شود
@client.on(events.NewMessage(pattern=r'^(?i)(\.play|پخش)$'))
async def play_handler(event):
    if not (event.out or event.sender_id in SUPER_USERS or event.chat_id == GROUP_CHAT_ID):
        return
        
    if not event.is_reply:
        await event.reply('❌ برای پخش، این دستور رو **روی یک فایل صوتی ریپلای کن**!')
        return

    reply_msg = await event.get_reply_message()

    if not reply_msg.media:
        await event.reply('❌ پیامی که ریپلای کردی فایل صوتی (آهنگ یا ویس) نداره!')
        return
        
    chat_id = event.chat_id
    status_msg = await event.reply('📥 در حال دریافت آهنگ... ⏳')
    
    try:
        # دانلود فایل و ذخیره با یک اسم ثابت برای جلوگیری از پر شدن حافظه رندر
        file_path = await reply_msg.download_media(file="downloads/current_song")
        
        await status_msg.edit('🎵 آهنگ آماده شد! در حال پخش در ویس‌چت... 🎧')
        
        # پخش آهنگ در ویس‌چت
        await app.play(
            chat_id,
            MediaStream(file_path)
        )
    except Exception as e:
        await status_msg.edit(f'❌ ارور در دانلود یا پخش آهنگ (مطمئن شو ویس‌چت روشنه):\n`{e}`')


# ── هندلر توقف آهنگ (فارسی و انگلیسی) ─────────────────────
# با تایپ کردن .stop یا کلمه "توقف" فعال می‌شود
@client.on(events.NewMessage(pattern=r'^(?i)(\.stop|توقف)$'))
async def stop_handler(event):
    if not (event.out or event.sender_id in SUPER_USERS or event.chat_id == GROUP_CHAT_ID):
        return
        
    chat_id = event.chat_id
    try:
        # ربات از ویس‌چت خارج می‌شود و آهنگ قطع می‌گردد
        await app.leave_call(chat_id)
        await event.reply('⏹ آهنگ با موفقیت متوقف شد.')
    except Exception as e:
        await event.reply(f'❌ ارور در توقف آهنگ:\n`{e}`')


# ── راه‌اندازی موتور اصلی ────────────────────────────────
async def start_music_worker():
    print("🚀 در حال استارت موتور Telethon...")
    await client.start()
    print("🎧 در حال استارت موتور PyTgCalls...")
    await app.start()
    print(f"✅ سیستم کاملاً آماده است! سوپریوزرها: {SUPER_USERS} | گروه مجاز: {GROUP_CHAT_ID}")
    
    # روشن نگه داشتن یوزربات
    await client.run_until_disconnected()