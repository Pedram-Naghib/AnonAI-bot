import os
import asyncio
from pyrogram import Client, filters
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped

# دریافت ثابت‌ها از لایه خنثی کانفیگ
from src.config import API_ID, API_HASH, SUPER_USERS, EMOJI

# کلاینت‌های اصلی یوزربات
music_app = None
call_py = None

if API_ID and API_HASH:
    music_app = Client("music_userbot", api_id=API_ID, api_hash=API_HASH)
    call_py = PyTgCalls(music_app)

    # ==========================================
    # 🎵 هندلر اصلی پخش موزیک (فایل تلگرام + یوتیوب)
    # ==========================================
    @music_app.on_message(filters.command("play") & filters.user(SUPER_USERS))
    async def play_music_handler(client, message):
        group_chat_id = message.chat.id
        args = message.text.split(maxsplit=1)
        
        # ── حالت اول: پخش فایل محلی/تلگرامی (از طریق ریپلای) ──
        if message.reply_to_message and (message.reply_to_message.audio or message.reply_to_message.voice):
            msg = await message.reply_text(f"{EMOJI['clock']['html']} در حال دانلود فایل صوتی از تلگرام...", parse_mode="HTML")
            try:
                file_path = await message.reply_to_message.download()
                await msg.edit_text(f"{EMOJI['update']['html']} در حال اتصال به ویس‌چت گروه...", parse_mode="HTML")
                
                await call_py.play(group_chat_id, AudioPiped(file_path))
                await msg.edit_text(f"{EMOJI['thunder']['html']} <b>فایل صوتی با موفقیت در ویس‌چت پخش شد!</b>", parse_mode="HTML")
            except Exception as e:
                await msg.edit_text(f"{EMOJI['ban']['html']} خطا در پخش فایل: <code>{e}</code>", parse_mode="HTML")
            return

        # ── حالت دوم: پخش از یوتیوب (لینک یا سرچ متنی) ──
        if len(args) < 2:
            await message.reply_text(f"{EMOJI['caution']['html']} لطفاً یا روی یک آهنگ ریپلای کنید، یا لینک/اسم آهنگ از یوتیوب را بفرستید.\nمثال:\n<code>/play https://youtube.com/...</code>", parse_mode="HTML")
            return
            
        search_query = args[1].strip()
        msg = await message.reply_text(f"{EMOJI['magnifiyer']['html']} در حال جستجو و آماده‌سازی از یوتیوب...", parse_mode="HTML")
        
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
            
            await msg.edit_text(f"{EMOJI['update']['html']} در حال استریم لایو آهنگ <b>{video_title}</b> در ویس‌چت...", parse_mode="HTML")
            
            # پخش موزیک دانلود شده از یوتیوب در ویس چت
            await call_py.play(group_chat_id, AudioPiped(file_path))
            await msg.edit_text(f"{EMOJI['check']['html']} <b>در حال پخش از یوتیوب:</b>\n🎵 <code>{video_title}</code>", parse_mode="HTML")
            
        except Exception as e:
            await msg.edit_text(f"{EMOJI['ban']['html']} خطایی در استخراج یا پخش از یوتیوب رخ داد:\n<code>{e}</code>", parse_mode="HTML")

    # ==========================================
    # ⏹️ هندلر قطع پخش و خروج از ویس‌چت
    # ==========================================
    @music_app.on_message(filters.command("stop") & filters.user(SUPER_USERS))
    async def stop_music_handler(client, message):
        try:
            await call_py.leave_group_call(message.chat.id)
            await message.reply_text(f"{EMOJI['trash']['html']} پخش موزیک متوقف شد و از ویس‌چت خارج شدم.", parse_mode="HTML")
        except Exception as e:
            await message.reply_text(f"{EMOJI['caution']['html']} خطایی در خروج از تماس رخ داد: {e}", parse_mode="HTML")

# تابع نهایی لودر هم‌زمان که در main.py صدا زده می‌شود
async def start_music_worker():
    if music_app and call_py:
        print("🎵 Initializing Music UserBot side-by-side...")
        await music_app.start()
        await call_py.start()
    else:
        print("⚠️ [Music Bot] API_ID or API_HASH missing in config. Worker skipped.")