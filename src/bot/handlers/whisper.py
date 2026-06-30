import uuid
import html
from telebot.async_telebot import AsyncTeleBot
from telebot.types import (
    InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

from src.config import EMOJI
from src.database.db_manager import get_or_create_short_link

# In-memory store — whispers are intentionally ephemeral and are lost on restart.
# Bounded so a long-running process can't leak memory: once full, the oldest
# whisper is evicted (dicts keep insertion order on Python 3.7+).
# If durable persistence is ever needed, move this to Redis with a TTL.
WHISPER_STORAGE: dict = {}
WHISPER_MAX = 5000


def _store_whisper(w_id: str, data: dict):
    if len(WHISPER_STORAGE) >= WHISPER_MAX:
        oldest = next(iter(WHISPER_STORAGE), None)
        if oldest is not None:
            WHISPER_STORAGE.pop(oldest, None)
    WHISPER_STORAGE[w_id] = data


def register_whisper_handlers(bot: AsyncTeleBot):

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

            # Parse "message\ntarget" or "message target"
            lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
            if len(lines) >= 2:
                target_user  = lines[-1]
                secret_text  = "\n".join(lines[:-1])
            else:
                parts = raw_text.rsplit(" ", 1)
                if len(parts) < 2:
                    return
                secret_text  = parts[0].strip()
                target_user  = parts[1].strip()

            if not target_user.startswith("@") and not target_user.isdigit():
                return

            w_id = str(uuid.uuid4())[:8]
            _store_whisper(w_id, {
                "sender_id":   sender_id,
                "sender_name": sender_name,
                "sender_tag":  sender_tag,
                "target":      target_user.lower(),
                "text":        secret_text,
                "is_opened":   False,
            })

            kb_initial = InlineKeyboardMarkup()
            kb_initial.row(
                InlineKeyboardButton(text=f"{EMOJI['whisper_wait']['char']} خواندن نجوا", callback_data=f"whopen_{w_id}", style="primary"),
                InlineKeyboardButton(text=f"{EMOJI['trash']['char']} حذف", callback_data=f"whdel_{w_id}", style="danger"),
            )

            await bot.answer_inline_query(
                query.id,
                [InlineQueryResultArticle(
                    id=w_id,
                    title=f"🔒 ارسال پیام محرمانه به {target_user}",
                    input_message_content=InputTextMessageContent(
                        f"📬 در انتظار خوانده شدن...\n🎯 <code>{html.escape(target_user)}</code>",
                        parse_mode="HTML"
                    ),
                    reply_markup=kb_initial,
                    description=f"نجوا به {target_user} ارسال شد"
                )],
                cache_time=0
            )

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

            kb_refresh = InlineKeyboardMarkup()
            kb_refresh.row(
                InlineKeyboardButton(text=f"{EMOJI['whisper_read']['char']} خواندن نجوا", callback_data=f"whopen_{w_id}", style="primary"),
                InlineKeyboardButton(text=f"{EMOJI['trash']['char']} حذف", callback_data=f"whdel_{w_id}", style="danger"),
            )

            if call.data.startswith("whopen_"):
                data = WHISPER_STORAGE.get(w_id)
                if not data:
                    await bot.answer_callback_query(call.id, "❌ این نجوا منقضی یا حذف شده است.", show_alert=True)
                    return

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

            kb = InlineKeyboardMarkup()
            kb.row(
                InlineKeyboardButton(text=f"{EMOJI['whisper_wait']['char']} خواندن نجوا", callback_data=f"whopen_{w_id}", style="primary"),
                InlineKeyboardButton(text=f"{EMOJI['trash']['char']} حذف", callback_data=f"whdel_{w_id}", style="danger"),
            )

            await bot.edit_message_text(
                f"{EMOJI['whisper_wait']['html']} در انتظار خوانده شدن...\n"
                f"{EMOJI['target']['html']} <code>{html.escape(target_user)}</code>",
                inline_message_id=inline_message_id,
                parse_mode="HTML", reply_markup=kb
            )
        except Exception as e:
            print(f"💥 Chosen Inline Error: {e}")