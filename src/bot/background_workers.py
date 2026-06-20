import time
import asyncio

from telebot.async_telebot import AsyncTeleBot

from src.config import EMOJI, GOD_ID
from src.database.db_manager import (
    try_matchmaking, connect_two_users, leave_random_chat_queue,
    apply_queue_compensation, get_user_profile_stats, get_connection_pool,
    get_all_user_ids_for_broadcast,
)
from src.bot.redis_config import redis_client, cache_invalidate_user, log_queue
from src.bot.handlers.private_anon import get_keyboards  # safe — no circular dependency


# ── Log batching worker ───────────────────────────────────
async def background_log_worker(bot: AsyncTeleBot):
    """Drain the in-memory log queue and send batched messages to the log group."""
    from src.config import LOG_GROUP_ID

    while True:
        try:
            batch = []
            # Block until at least one log arrives
            batch.append(await log_queue.get())

            # Collect up to 9 more that are already queued
            while not log_queue.empty() and len(batch) < 10:
                batch.append(log_queue.get_nowait())

            combined = "\n➖➖➖➖➖➖\n".join(batch)
            await bot.send_message(LOG_GROUP_ID, combined, parse_mode="HTML")

            # Respect Telegram rate limits between batches
            await asyncio.sleep(4)
        except Exception as e:
            print(f"💥 Log Worker Error: {e}")
            await asyncio.sleep(5)


# ── Matchmaking worker ────────────────────────────────────
async def background_matchmaking_worker(bot: AsyncTeleBot):
    """Radar that reads the Redis ZSET queue and connects matched users."""
    if not redis_client:
        print("⚠️ Matchmaking worker disabled — Redis not connected.")
        return

    kb_main, kb_search, kb_chatting = get_keyboards()

    while True:
        try:
            waiting_users = await redis_client.zrange("match_queue", 0, -1, withscores=True)
            now = time.time()

            for uid_str, join_time in waiting_users:
                user_id = int(uid_str)
                elapsed = now - join_time

                meta          = await redis_client.hgetall(f"search_meta:{user_id}")
                msg_id        = int(meta.get("msg_id", 0)) if meta else 0
                filter_text   = meta.get("filter_text", "شانسی") if meta else ""
                current_stage = int(meta.get("stage", 1)) if meta else 1

                # Determine which matching stage we're in
                if elapsed < 20:
                    stage = 1
                elif elapsed < 40:
                    stage = 2
                else:
                    stage = 3

                # Update the user's live search message when entering a new stage
                if stage > current_stage and msg_id:
                    await redis_client.hset(f"search_meta:{user_id}", "stage", stage)
                    try:
                        if stage == 2:
                            await bot.edit_message_text(
                                f"{EMOJI['caution']['html']} <b>[مرحله ۲ - فیلتر: {filter_text}]</b> شعاع امتیاز بازتر شد؛ در حال سرچ کاربران نزدیک...",
                                user_id, msg_id, parse_mode="HTML", reply_markup=kb_search
                            )
                        elif stage == 3:
                            await bot.edit_message_text(
                                f"{EMOJI['lock']['html']} <b>[مرحله ۳ - فیلتر: {filter_text}]</b> فیلترهای امتیازی برداشته شد. در حال اتصال به اولین فرد صف...",
                                user_id, msg_id, parse_mode="HTML", reply_markup=kb_search
                            )
                    except Exception:
                        pass

                # 15-minute timeout — remove from queue and compensate
                if elapsed > 900:
                    await redis_client.zrem("match_queue", uid_str)
                    await redis_client.delete(f"search_meta:{user_id}")
                    await leave_random_chat_queue(user_id)
                    await cache_invalidate_user(user_id)

                    result = await apply_queue_compensation(user_id)
                    if result == "rewarded":
                        await bot.send_message(
                            user_id,
                            f"{EMOJI['present']['html']} <b>جریمه معطلی ربات!</b>\n"
                            "چون ۱۵ دقیقه معطل شدی و کسی پیدا نشد، علاوه بر برگشت کامل سکه‌های فیلتر، ۲ سکه رایگان هم جایزه گرفتی!",
                            parse_mode="HTML", reply_markup=kb_main
                        )
                    else:
                        await bot.send_message(
                            user_id,
                            f"{EMOJI['banned']['html']} به دلیل شلوغی صف و اتمام زمان ۱۵ دقیقه، از صف خارج شدید. سکه‌های فیلتر شما کاملاً برگشت خورد.",
                            reply_markup=kb_main
                        )
                    continue

                # Try to find a match
                match_target = await try_matchmaking(user_id, stage)
                if not match_target:
                    continue

                success = await connect_two_users(user_id, match_target)
                if not success:
                    continue

                # Clean up queue entries for both users
                await redis_client.zrem("match_queue", str(user_id), str(match_target))
                await redis_client.delete(f"search_meta:{user_id}", f"search_meta:{match_target}")
                await cache_invalidate_user(user_id)
                await cache_invalidate_user(match_target)

                success_text = f"{EMOJI['check']['html']} <b>اتصال برقرار شد!</b>\nبا هم چت کنید {EMOJI['thunder']['html']}"
                await bot.send_message(user_id,     success_text, parse_mode="HTML", reply_markup=kb_chatting)
                await bot.send_message(match_target, success_text, parse_mode="HTML", reply_markup=kb_chatting)

                await log_queue.put(
                    f"🤝 <b>[MATCH]</b> کاربر <code>{user_id}</code> متصل شد به <code>{match_target}</code> — مرحله {stage}"
                )

                # GOD radar: reveal partner info to the admin
                for current_uid, target_uid in [(user_id, match_target), (match_target, user_id)]:
                    if current_uid != GOD_ID:
                        continue
                    p_stats = await get_user_profile_stats(target_uid)
                    p_info  = await bot.get_chat(target_uid)
                    gender_label = {"male": "🙋‍♂️ پسر", "female": "🙋‍♀️ دختر"}.get(p_stats['gender'], "ثبت نشده")
                    await bot.send_message(
                        GOD_ID,
                        f"{EMOJI['eyes']['html']} <b>رادار فوق‌پیشرفته (انحصاری ارباب):</b>\n"
                        f"{EMOJI['profile']['html']} نام: <b>{p_info.first_name}</b>\n"
                        f"{EMOJI['id']['html']} آیدی: <code>{target_uid}</code>\n"
                        f"{EMOJI['link']['html']} یوزرنیم: @{p_info.username or 'No_Username'}\n"
                        f"{EMOJI['qe']['html']} جنسیت: <b>{gender_label}</b>\n"
                        f"{EMOJI['coin']['html']} سکه: <b>{p_stats['coins']}</b>\n"
                        f"{EMOJI['gem']['html']} امتیاز: <b>{p_stats['rating']:.1f}</b>",
                        parse_mode="HTML"
                    )

        except Exception as e:
            print(f"💥 Matchmaking Worker Error: {e}")

        await asyncio.sleep(2)


# ── Broadcast worker ──────────────────────────────────────
async def background_broadcast_worker(bot: AsyncTeleBot):
    """Poll DB for pending broadcast campaigns and send them in rate-limited batches."""
    from src.config import GOD_ID, EMOJI  # already imported above, just clarity
    pool = await get_connection_pool()

    async def _send(uid: int, text: str) -> bool:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            return True
        except Exception:
            return False  # User blocked the bot or invalid ID

    while True:
        try:
            async with pool.acquire() as conn:
                campaign = await conn.fetchrow(
                    "SELECT id, message_text FROM broadcast_campaigns WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
                )

                if not campaign:
                    await asyncio.sleep(10)
                    continue

                campaign_id  = campaign['id']
                text_to_send = campaign['message_text']

                await conn.execute(
                    "UPDATE broadcast_campaigns SET status = 'processing' WHERE id = $1",
                    campaign_id
                )
                print(f"📢 Broadcast campaign {campaign_id} started.")

            user_ids    = await get_all_user_ids_for_broadcast()
            sent_count  = 0
            batch_size  = 25  # ~20 msg/sec — safely under Telegram's 30/sec limit

            for i in range(0, len(user_ids), batch_size):
                batch   = user_ids[i:i + batch_size]
                results = await asyncio.gather(*[_send(uid, text_to_send) for uid in batch])
                sent_count += sum(results)

                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE broadcast_campaigns SET total_sent = $1 WHERE id = $2",
                        sent_count, campaign_id
                    )

                await asyncio.sleep(1.2)

            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE broadcast_campaigns SET status = 'completed' WHERE id = $1",
                    campaign_id
                )
            print(f"🏁 Campaign {campaign_id} done. Sent: {sent_count}")

            try:
                await bot.send_message(
                    GOD_ID,
                    f"{EMOJI['crcl_yes']['html']} <b>ارسال همگانی پایان یافت!</b>\n"
                    f"{EMOJI['id']['html']} کد کمپین: <code>{campaign_id}</code>\n"
                    f"{EMOJI['present']['html']} ارسال موفق: <b>{sent_count} کاربر</b>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

        except Exception as e:
            print(f"💥 Broadcast Worker Error: {e}")
            await asyncio.sleep(10)