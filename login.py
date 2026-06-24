import socks
from telethon import TelegramClient

# تنظیمات پروکسی اصلاح‌شده بر اساس پورت HTTP در v2rayN (حالت Mixed)
# پورت 10809 پورت پیش‌فرض HTTP برای v2rayN است که فایروال راحت‌تر باهاش کنار میاد.
PROXY = (socks.HTTP, '192.168.146.2', 10809) 

# مشخصات API تلگرام شما
api_id = 000
api_hash = 'hey'

# ساخت کلاینت تله‌تون با پروکسی اصلاح شده
client = TelegramClient("music_userbot", api_id, api_hash, proxy=PROXY)

async def main():
    print("🚀 در حال اتصال به تلگرام از طریق پروکسی HTTP...")
    
    # استارت کلاینت (اگر بار اول باشد، در ترمینال از شما شماره تلفن و کد می‌خواهد)
    await client.start()
    
    print("✅ سشن با موفقیت ساخته شد!")
    
    # ارسال یک پیام به Saved Messages خودت برای تست نهایی اتصال
    await client.send_message('me', 'سلام پدرام! یوزربات با موفقیت متصل شد و فایروال دور زده شد. 😎')
    print("📩 پیام تست با موفقیت به Saved Messages ارسال شد.")

# اجرای اسکریپت
if __name__ == '__main__':
    with client:
        client.loop.run_until_complete(main())
