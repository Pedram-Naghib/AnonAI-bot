import re
import asyncio
import traceback

from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardRemove, InputSticker

from src.config import GROUP_CHAT_ID, EMOJI, GOD_ID, SUPER_USERS
from src.database.db_manager import get_connection_pool


def register_admin_handlers(bot: AsyncTeleBot):

    # ── /id — get chat/group ID ───────────────────────────
    @bot.message_handler(commands=['id'])
    async def handle_get_chat_id(message):
        try:
            await bot.reply_to(
                message,
                f"{EMOJI['id']['html']} آیدی این چت/گروه: <code>{message.chat.id}</code>",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"❌ /id error: {e}")

    # ── /gp — send message to group ──────────────────────
    @bot.message_handler(commands=['gp'])
    async def handle_send_msg_to_gp(message):
        if message.chat.id not in SUPER_USERS:
            return
        try:
            parts = message.text.split("/gp ", 1)
            if len(parts) > 1:
                await bot.send_message(GROUP_CHAT_ID, parts[-1], reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            print(f"❌ /gp error: {e}")

    # ── Auto-reply by private group link ─────────────────
    @bot.message_handler(regexp=r"^https:\/\/t\.me\/c\/1434396268\/(\d+)\s+(.*)")
    async def handle_auto_reply_by_link(message):
        if message.chat.id not in SUPER_USERS:
            return
        try:
            match = re.match(r"^https:\/\/t\.me\/c\/1434396268\/(\d+)\s+(.*)", message.text)
            if match:
                reply_to_msg_id = int(match.group(1))
                clean_text      = match.group(2)
                await bot.send_message(
                    GROUP_CHAT_ID, text=clean_text,
                    reply_to_message_id=reply_to_msg_id,
                    reply_markup=ReplyKeyboardRemove()
                )
                await bot.reply_to(
                    message,
                    f"{EMOJI['target']['html']} روی پیام <code>{reply_to_msg_id}</code> ریپلای شد!",
                    parse_mode="HTML"
                )
        except Exception as e:
            print(f"❌ Auto-reply error: {e}")

    # ── /db_stats — advanced user database report ─────────
    @bot.message_handler(
        commands=['db_stats'],
        func=lambda m: m.chat.type == "private" and m.from_user.id in SUPER_USERS
    )
    async def handle_god_db_stats(message):
        await bot.send_chat_action(message.chat.id, 'typing')
        pool = await get_connection_pool()

        try:
            async with pool.acquire() as conn:
                total_users      = await conn.fetchval("SELECT COUNT(*) FROM users")
                total_dead_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE anon_state = 'blocked_bot'")

                rows = await conn.fetch("""
                    SELECT
                        u.user_id,
                        u.first_name,
                        u.username,
                        u.total_received AS received,
                        u.total_sent     AS sent
                    FROM users u
                    WHERE u.anon_state != 'blocked_bot'
                    ORDER BY (u.total_received + u.total_sent) DESC
                    LIMIT 30
                """)

            if not rows:
                await bot.reply_to(
                    message,
                    f"{EMOJI['whisper_read']['html']} هیچ کاربری یافت نشد.\n👥 کل اعضا: {total_users}",
                    parse_mode="HTML"
                )
                return

            # Check each user is still reachable (hasn't blocked the bot)
            async def _is_alive(row) -> tuple:
                try:
                    await asyncio.wait_for(
                        bot.send_chat_action(row['user_id'], 'typing'),
                        timeout=1.5
                    )
                    return row, True
                except Exception:
                    async with pool.acquire() as db_conn:
                        await db_conn.execute(
                            "UPDATE users SET anon_state = 'blocked_bot', chat_status = 'idle', active_partner_id = NULL WHERE user_id = $1",
                            row['user_id']
                        )
                    return row, False

            checked = await asyncio.gather(*[_is_alive(row) for row in rows])

            live_count = total_users - total_dead_users
            lines = [
                f"{EMOJI['gem']['html']} <b>گزارش ارشد وضعیت دیتابیس</b>\n",
                f"{EMOJI['profile']['html']} کل کاربران ثبت شده: <b>{total_users}</b>",
                f"{EMOJI['green_dot']['html']} کاربران فعال: <b>{live_count}</b>",
                f"{EMOJI['red_dot']['html']} مسدودکنندگان: <b>{total_dead_users}</b>\n",
                f"{EMOJI['magnifiyer']['html']} <i>۲۰ کاربر برتر بر اساس بیشترین تعامل:</i>\n",
            ]

            valid = 0
            for row, is_active in checked:
                if not is_active:
                    continue
                valid += 1
                username = f"@{row['username']}" if row['username'] else "بدون یوزرنیم"
                lines.append(
                    f"{valid}. {EMOJI['profile']['html']} <b>{row['first_name'] or 'Unknown'}</b> "
                    f"(<code>{row['user_id']}</code>) | {username}\n"
                    f"   {EMOJI['recieve']['html']} دریافتی: <b>{row['received']}</b> | "
                    f"{EMOJI['send']['html']} ارسالی: <b>{row['sent']}</b>\n   ➖"
                )
                if valid >= 20:
                    break

            await bot.reply_to(message, "\n".join(lines), parse_mode="HTML")

        except Exception as e:
            print(f"💥 /db_stats error: {e}")
            traceback.print_exc()
            await bot.reply_to(
                message,
                f"{EMOJI['ban']['html']} خطای فنی در استخراج اطلاعات.",
                parse_mode="HTML"
            )

    # ── /bc — bulk broadcast ──────────────────────────────
    @bot.message_handler(
        commands=['bc'],
        func=lambda m: m.chat.type == "private" and m.from_user.id in SUPER_USERS
    )
    async def handle_bulk_broadcast(message):
        try:
            parts = message.text.split("/bc ", 1)
            if len(parts) < 2 or not parts[1].strip():
                await bot.reply_to(
                    message,
                    f"{EMOJI['caution']['html']} <b>فرمت اشتباه!</b>\n"
                    "مثال: <code>/bc سلام کاربران، نسخه جدید منتشر شد!</code>",
                    parse_mode="HTML"
                )
                return

            from src.database.db_manager import create_broadcast_campaign
            campaign_id = await create_broadcast_campaign(parts[1].strip())

            await bot.reply_to(
                message,
                f"{EMOJI['thunder']['html']} <b>فرمان ارسال همگانی صادر شد!</b>\n\n"
                f"{EMOJI['id']['html']} کد کمپین: <code>{campaign_id}</code>\n"
                f"{EMOJI['clock']['html']} وضعیت: <i>در صف ارسال...</i>\n\n"
                f"پس از اتمام، گزارش نهایی ارسال می‌شود. {EMOJI['sus']['html']}",
                parse_mode="HTML"
            )

        except Exception as e:
            print(f"💥 /bc error: {e}")
            await bot.reply_to(
                message,
                f"{EMOJI['ban']['html']} خطای فنی در ثبت کمپین.",
                parse_mode="HTML"
            )

    # ── /emoji — list all registered premium emojis ───────
    @bot.message_handler(
        commands=["emoji"],
        func=lambda m: m.chat.id in SUPER_USERS
    )
    async def send_emojis(message):
        try:
            for key, value in EMOJI.items():
                await bot.send_message(
                    message.chat.id,
                    f"{EMOJI['pin']['html']} <b>Key:</b> <code>{key}</code>\n"
                    f"{EMOJI['ball']['html']} <b>Render:</b> {value['html']}",
                    parse_mode="HTML"
                )
                # FIX: added sleep to avoid Telegram flood control (30 msg/sec limit)
                await asyncio.sleep(0.05)
        except Exception as e:
            print(f"💥 /emoji error: {e}")

    # ── Emoji pack helpers ────────────────────────────────
    async def _get_file_details(msg):
        """Extract file_id, format, and emoji from a replied-to sticker/emoji/document."""
        if not msg.reply_to_message:
            return None, None, None
        reply = msg.reply_to_message

        if reply.sticker:
            fmt = "animated" if reply.sticker.is_animated else ("video" if reply.sticker.is_video else "static")
            return reply.sticker.file_id, fmt, reply.sticker.emoji

        entities = reply.entities or reply.caption_entities
        if entities:
            for ent in entities:
                if ent.type == 'custom_emoji':
                    stickers = await bot.get_custom_emoji_stickers([ent.custom_emoji_id])
                    if stickers:
                        s   = stickers[0]
                        fmt = "animated" if s.is_animated else ("video" if s.is_video else "static")
                        return s.file_id, fmt, s.emoji

        doc = reply.document or reply.video
        if doc:
            name = getattr(doc, 'file_name', '').lower()
            if name.endswith('.tgs') or getattr(doc, 'is_animated', False):
                fmt = "animated"
            elif name.endswith('.webm') or getattr(doc, 'is_video', False):
                fmt = "video"
            else:
                fmt = "static"
            return doc.file_id, fmt, None

        return None, None, None

    async def _full_pack_name(short_name: str) -> str:
        """Append _by_<botusername> suffix if not already present."""
        bot_info  = await bot.get_me()
        suffix    = f"_by_{bot_info.username}"
        return short_name if short_name.endswith(suffix) else f"{short_name}{suffix}"

    # ── /create_pack ──────────────────────────────────────
    @bot.message_handler(commands=['create_pack'], func=lambda m: m.chat.id in SUPER_USERS)
    async def admin_create_pack(message):
        try:
            args = message.text.split(maxsplit=3)
            if len(args) < 3:
                await bot.reply_to(
                    message,
                    f"{EMOJI['caution']['html']} فرمت:\n"
                    "<code>/create_pack pack_name Title [🎯]</code>",
                    parse_mode="HTML"
                )
                return

            short_name, title                = args[1], args[2]
            file_id, fmt, extracted_emoji    = await _get_file_details(message)

            if not file_id:
                await bot.reply_to(message, f"{EMOJI['ban']['html']} روی یک اموجی پرمیوم یا فایل ریپلای کن!", parse_mode="HTML")
                return

            emoji = args[3] if len(args) > 3 else extracted_emoji
            if not emoji:
                await bot.reply_to(message, f"{EMOJI['ban']['html']} اموجی پیدا نشد. خودت اموجی رو آخر دستور بنویس.", parse_mode="HTML")
                return

            full_name = await _full_pack_name(short_name)
            sticker   = InputSticker(sticker=file_id, emoji_list=[emoji])
            status_msg = await bot.reply_to(message, f"{EMOJI['clock']['html']} در حال ساخت پک...", parse_mode="HTML")

            success = await bot.create_new_sticker_set(
                user_id=GOD_ID, name=full_name,
                title=title.replace("_", " "),
                stickers=[sticker], sticker_format=fmt, sticker_type="custom_emoji"
            )

            if success:
                pack    = await bot.get_sticker_set(full_name)
                new_id  = pack.stickers[0].custom_emoji_id
                await bot.edit_message_text(
                    f"{EMOJI['crcl_yes']['html']} <b>پک ساخته شد!</b>\n\n"
                    f"{EMOJI['present']['html']} نام: <code>{full_name}</code>\n"
                    f"{EMOJI['link']['html']} <a href='https://t.me/addstickers/{full_name}'>لینک پک</a>\n\n"
                    f"{EMOJI['gem']['html']} <b>Custom Emoji ID:</b>\n<code>{new_id}</code>",
                    message.chat.id, status_msg.message_id,
                    parse_mode="HTML", disable_web_page_preview=True
                )
        except Exception as e:
            await bot.reply_to(message, f"{EMOJI['bang']['html']} خطا در ساخت پک:\n<code>{e}</code>", parse_mode="HTML")

    # ── /add_emoji ────────────────────────────────────────
    @bot.message_handler(commands=['add_emoji'], func=lambda m: m.chat.id in SUPER_USERS)
    async def admin_add_emoji(message):
        try:
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                await bot.reply_to(
                    message,
                    f"{EMOJI['caution']['html']} فرمت:\n<code>/add_emoji pack_name [🎯]</code>",
                    parse_mode="HTML"
                )
                return

            pack_name                     = args[1]
            file_id, fmt, extracted_emoji = await _get_file_details(message)

            if not file_id:
                await bot.reply_to(message, f"{EMOJI['ban']['html']} روی یک فایل یا اموجی پرمیوم ریپلای کن!", parse_mode="HTML")
                return

            emoji = args[2] if len(args) > 2 else extracted_emoji
            if not emoji:
                await bot.reply_to(message, f"{EMOJI['ban']['html']} اموجی تشخیص داده نشد.", parse_mode="HTML")
                return

            full_name  = await _full_pack_name(pack_name)
            sticker    = InputSticker(sticker=file_id, emoji_list=[emoji])
            status_msg = await bot.reply_to(message, f"{EMOJI['clock']['html']} در حال افزودن اموجی...", parse_mode="HTML")

            success = await bot.add_sticker_to_set(user_id=GOD_ID, name=full_name, sticker=sticker)
            if success:
                pack   = await bot.get_sticker_set(full_name)
                new_id = pack.stickers[-1].custom_emoji_id
                await bot.edit_message_text(
                    f"{EMOJI['crcl_yes']['html']} <b>اموجی اضافه شد!</b>\n\n"
                    f"{EMOJI['gem']['html']} <b>Custom Emoji ID:</b>\n<code>{new_id}</code>",
                    message.chat.id, status_msg.message_id, parse_mode="HTML"
                )
        except Exception as e:
            if "STICKER_FORMAT_INVALID" in str(e):
                await bot.reply_to(
                    message,
                    f"{EMOJI['red_caution']['html']} <b>خطای فرمت:</b> فرمت اموجی با پک مطابقت ندارد!",
                    parse_mode="HTML"
                )
            else:
                await bot.reply_to(message, f"{EMOJI['bang']['html']} خطا:\n<code>{e}</code>", parse_mode="HTML")

    # ── /list_pack ────────────────────────────────────────
    @bot.message_handler(commands=['list_pack'], func=lambda m: m.chat.id in SUPER_USERS)
    async def admin_list_pack(message):
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await bot.reply_to(message, f"{EMOJI['caution']['html']} فرمت:\n<code>/list_pack pack_name</code>", parse_mode="HTML")
                return

            full_name = await _full_pack_name(args[1])
            pack      = await bot.get_sticker_set(full_name)

            res = f"{EMOJI['present']['html']} <b>پک:</b> <code>{pack.title}</code>\nتعداد: {len(pack.stickers)}\n\n"
            for i, s in enumerate(pack.stickers):
                res += (
                    f"[{i+1}] {s.emoji}\n"
                    f"{EMOJI['gem']['html']} <b>Custom ID:</b> <code>{s.custom_emoji_id}</code>\n"
                    f"{EMOJI['trash']['html']} <b>File ID:</b> <code>{s.file_id}</code>\n\n"
                )

            # Send in chunks to respect Telegram's 4096 char limit
            for chunk in range(0, len(res), 4000):
                await bot.send_message(message.chat.id, res[chunk:chunk+4000], parse_mode="HTML")

        except Exception as e:
            await bot.reply_to(message, f"{EMOJI['bang']['html']} خطا:\n<code>{e}</code>", parse_mode="HTML")

    # ── /del_emoji ────────────────────────────────────────
    @bot.message_handler(commands=['del_emoji'], func=lambda m: m.chat.id in SUPER_USERS)
    async def admin_del_emoji(message):
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await bot.reply_to(
                    message,
                    f"{EMOJI['caution']['html']} فرمت:\n<code>/del_emoji FILE_ID</code>\n"
                    "فایل آیدی را از /list_pack بگیر.",
                    parse_mode="HTML"
                )
                return

            success = await bot.delete_sticker_from_set(args[1].strip())
            if success:
                await bot.reply_to(message, f"{EMOJI['trash']['html']} <b>اموجی حذف شد!</b>", parse_mode="HTML")

        except Exception as e:
            await bot.reply_to(message, f"{EMOJI['bang']['html']} خطا:\n<code>{e}</code>", parse_mode="HTML")