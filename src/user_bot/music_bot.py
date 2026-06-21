import os
import asyncio
from telethon import TelegramClient, events
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

# دریافت ثابت‌ها از لایه خنثی کانفیگ
from src.config import API_ID, API_HASH, SUPER_USERS, EMOJI

# کلاینت‌های اصلی یوزربات
music_app = None
call_py = None

if API_ID and API_HASH:
    # ساخت کلاینت تله‌تون (فایل سشن با نام music_userbot.session ذخیره می‌شود)
    music_app = TelegramClient("music_userbot", API_ID, API_HASH)
    call_py = PyTgCalls(music_app)

    # ==========================================
    # 🎵 هندلر اصلی پخش موزیک (فایل تلگرام + یوتیوب)
    # ==========================================
    @music_app.on(events.NewMessage(pattern=r'^/play(?:\s+(.+))?$', from_users=SUPER_USERS))
    async def play_music_handler(event):
        group_chat_id = event.chat_id
        
        # استخراج متن جلوی کامند (اگر وجود داشته باشد)
        arg = event.pattern_match.group(1)
        
        # ── حالت اول: پخش فایل محلی/تلگرامی (از طریق ریپلای) ──
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg.audio or reply_msg.voice:
                msg = await event.reply(f"{EMOJI['clock']['html']} در حال دانلود فایل صوتی از تلگرام...", parse_mode="HTML")
                try:
                    file_path = await reply_msg.download_media()
                    await msg.edit(f"{EMOJI['update']['html']} در حال اتصال به ویس‌چت گروه...", parse_mode="HTML")
                    
                    await call_py.play(group_chat_id, MediaStream(file_path))
                    await msg.edit(f"{EMOJI['thunder']['html']} <b>فایل صوتی با موفقیت در ویس‌چت پخش شد!</b>", parse_mode="HTML")
                except Exception as e:
                    await msg.edit(f"{EMOJI['ban']['html']} خطا در پخش فایل: <code>{e}</code>", parse_mode="HTML")
                return

        # ── حالت دوم: پخش از یوتیوب (لینک یا سرچ متنی) ──
        if not arg:
            await event.reply(f"{EMOJI['caution']['html']} لطفاً یا روی یک آهنگ ریپلای کنید، یا لینک/اسم آهنگ از یوتیوب را بفرستید.\nمثال:\n<code>/play https://youtube.com/...</code>", parse_mode="HTML")
            return
            
        search_query = arg.strip()
        msg = await event.reply(f"{EMOJI['magnifiyer']['html']} در حال جستجو و آماده‌سازی از یوتیوب...", parse_mode="HTML")
        
        # پاتک محلی زنده برای استفاده از yt_dlp بدون قفل کردن پردازنده
        import yt_dlp
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'default_search': 'ytsearch', # اگر لینک نبود، خودش در یوتیوب سرچ میکند
            'outtmpl': 'downloads/%(id)s.%(ext)s',
        }
        
        def extract_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=True)
                # بررسی اینکه آیا نتیجه جستجو (لیست) است یا لینک مستقیم
                v_info = info['entries'][0] if 'entries' in info else info
                # گرفتن مسیر فایل دانلودی در همان اسکوپ
                f_path = ydl.prepare_filename(v_info)
                return v_info, f_path

        try:
            # اجرای دانلود یوتیوب در یک Thread جداگانه تا متد آسنکرون ربات کراش نزند
            loop = asyncio.get_running_loop()
            video_info, file_path = await loop.run_in_executor(None, extract_info)
                
            video_title = video_info.get('title', 'YouTube Audio')
            
            await msg.edit(f"{EMOJI['update']['html']} در حال استریم لایو آهنگ <b>{video_title}</b> در ویس‌چت...", parse_mode="HTML")
            
            # پخش موزیک دانلود شده از یوتیوب در ویس چت
            await call_py.play(group_chat_id, MediaStream(file_path))
            await msg.edit(f"{EMOJI['check']['html']} <b>در حال پخش از یوتیوب:</b>\n🎵 <code>{video_title}</code>", parse_mode="HTML")
            
        except Exception as e:
            await msg.edit(f"{EMOJI['ban']['html']} خطایی در استخراج یا پخش از یوتیوب رخ داد:\n<code>{e}</code>", parse_mode="HTML")

    # ==========================================
    # ⏹️ هندلر قطع پخش و خروج از ویس‌چت
    # ==========================================
    @music_app.on(events.NewMessage(pattern=r'^/stop$', from_users=SUPER_USERS))
    async def stop_music_handler(event):
        try:
            await call_py.leave_group_call(event.chat_id)
            await event.reply(f"{EMOJI['trash']['html']} پخش موزیک متوقف شد و از ویس‌چت خارج شدم.", parse_mode="HTML")
        except Exception as e:
            await event.reply(f"{EMOJI['caution']['html']} خطایی در خروج از تماس رخ داد: {e}", parse_mode="HTML")

# تابع نهایی لودر هم‌زمان که در main.py صدا زده می‌شود
async def start_music_worker():
    if music_app and call_py:
        print("🎵 Initializing Music UserBot side-by-side (Telethon Engine)...")
        await music_app.start()
        await call_py.start()
    else:
        print("⚠️ [Music Bot] API_ID or API_HASH missing in config. Worker skipped.")