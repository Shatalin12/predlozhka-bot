import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# ==================== НАСТРОЙКИ ====================
# На Railway токен берётся из Variables (переменных окружения).
# Локально, если переменной нет — используется токен ниже.
TOKEN = os.getenv("TOKEN", "8608207756:AAFTO0DyEq8q-I94ECiYRQ-vYQmrGQ0N_Ko")
ADMIN_CHAT_ID = -1003948032613
CHANNEL_ID = "@tb72tb72"
AUTO_ADD_USERNAME = True

# Прокси нужен ТОЛЬКО для локального запуска через Napp.
# На Railway он не нужен — Telegram там доступен напрямую.
# Для локального запуска раскомментируй строки с PROXY и session.
# PROXY = "socks5://127.0.0.1:10808"
# ===================================================

# Локальный запуск (раскомментировать при работе через Napp):
# from aiogram.client.session.aiohttp import AiohttpSession
# session = AiohttpSession(proxy=PROXY)
# bot = Bot(token=TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))

# Хостинг (Railway) — используется по умолчанию:
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

pending = {}
editing = {}
stats = {"received": 0, "published": 0, "rejected": 0}


class Form(StatesGroup):
    waiting_choice = State()
    waiting_photo = State()


# ==================== ТЕКСТЫ ====================

REVIEW_WARNING = (
    "⏳ <b>Важно:</b> заявки рассматриваются <b>в течение дня</b>.\n"
    "Пожалуйста, не отправляй одно и то же фото несколько раз — "
    "это не ускорит рассмотрение."
)

RULES = (
    "📜 <b>Правила канала</b>\n\n"
    "<b>Публикуем:</b>\n"
    "• анкеты для знакомств — фото, имя/псевдоним, пара слов о себе\n"
    "• фото — селфи, повседневные, атмосферные (без 18+)\n"
    "• запросы: ищу друзей / компанию / вторую половинку\n\n"
    "<b>Не публикуем:</b>\n"
    "🚫 оскорбления и травлю\n"
    "🚫 жестокость\n"
    "🚫 политику и конфликты\n"
    "🚫 18+\n"
    "🚫 криминал (наркотики, оружие)\n"
    "🚫 персональные данные\n"
    "🚫 фейки и чужой контент без источника\n\n"
    "✅ Уважаем людей.\n"
    "Сомневаешься — не отправляй."
)

USER_HELP = (
    "📖 <b>Что умеет этот бот</b>\n\n"
    "Это бот-предложка для канала знакомств.\n"
    "Ты можешь:\n"
    "• отправить <b>фото</b> (с подписью или без) — станет заявкой\n"
    "• <b>переслать боту пост из канала</b> — предложить его изменить\n\n"
    "<b>Как отправить:</b>\n"
    "1. Жми <b>📤 Отправить</b>\n"
    "2. Выбери: <b>С @username</b> или <b>🕶 Анонимно</b>\n"
    "3. Отправь фото\n"
    "4. Жди уведомления\n\n"
    "⏳ <b>Заявки рассматриваются в течение дня.</b>\n\n"
    "<b>Команды:</b>\n"
    "/start — начать заново\n"
    "/help — эта справка\n"
    "/cancel — отменить действие"
)

USER_ABOUT = (
    "ℹ️ <b>О боте</b>\n\n"
    "Бот-предложка для канала знакомств.\n"
    "Отправь фото — админ рассмотрит и, если ок, опубликует.\n\n"
    "⏳ <b>Срок рассмотрения:</b> в течение дня.\n\n"
    "Если хочешь — публикация будет анонимной."
)

ADMIN_HELP = (
    "🛠 <b>Меню администратора</b>\n\n"
    "<b>Кнопки на каждом сообщении:</b>\n"
    "✅ Опубликовать — фото уйдёт в канал\n"
    "❌ Отклонить — автору придёт отказ\n"
    "✏️ Изменить подпись — ответь новым текстом на сообщение бота\n"
    "🔄 Сбросить правку — вернуть оригинал автора\n"
    "🗑 Удалить пост — удалить опубликованное сообщение из канала\n\n"
    "<b>Команды:</b>\n"
    "/help — это меню\n"
    "/cancel — отменить редактирование\n"
    "/stats — статистика\n"
    "/last — последние 5 предложек"
)


# ==================== КЛАВИАТУРЫ ====================

def user_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📤 Отправить")],
            [KeyboardButton(text="📜 Правила"), KeyboardButton(text="📖 Помощь")],
            [KeyboardButton(text="ℹ️ О боте")],
        ],
        resize_keyboard=True,
    )


def admin_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛠 Помощь"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📋 Последние")],
        ],
        resize_keyboard=True,
    )


def start_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Отправить предложку", callback_data="menu:send")],
        [
            InlineKeyboardButton(text="📜 Правила", callback_data="menu:rules"),
            InlineKeyboardButton(text="📖 Помощь",  callback_data="menu:help"),
        ],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="menu:about")],
    ])


def mode_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👤 С моим @username", callback_data="mode:user"),
        InlineKeyboardButton(text="🕶 Анонимно",        callback_data="mode:anon"),
    ]])


def build_admin_caption(info):
    if info["anon"]:
        mark = "🕶 <b>Анонимно</b>"
    elif info["username"]:
        mark = f"👤 Автор: @{info['username']}"
    else:
        mark = f"👤 Автор: {info['full_name']} (id {info['user_id']})"

    if info.get("forwarded_from_channel"):
        mark += "\n🔁 <i>Переслано из канала</i>"

    cap = info["edited_caption"] if info["edited_caption"] is not None else info["caption"]
    return f"{mark}\n\n{cap}" if cap else mark


def build_admin_kb(user_msg_id, published=False):
    rows = [
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"pub:{user_msg_id}"),
            InlineKeyboardButton(text="❌ Отклонить",   callback_data=f"rej:{user_msg_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Изменить подпись", callback_data=f"edit:{user_msg_id}"),
            InlineKeyboardButton(text="🔄 Сбросить правку",  callback_data=f"reset:{user_msg_id}"),
        ],
    ]
    if published:
        rows.append([
            InlineKeyboardButton(text="🗑 Удалить пост", callback_data=f"del:{user_msg_id}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ==================== ОБЩИЕ КОМАНДЫ ====================

@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    await state.clear()
    if msg.chat.id == ADMIN_CHAT_ID:
        await msg.answer(ADMIN_HELP, reply_markup=admin_reply_menu())
        return
    await msg.answer(USER_HELP, reply_markup=user_reply_menu())
    await msg.answer(REVIEW_WARNING)
    await msg.answer("Что делаем?", reply_markup=start_inline_kb())


@dp.message(Command("help"))
async def cmd_help(msg: types.Message):
    if msg.chat.id == ADMIN_CHAT_ID:
        await msg.answer(ADMIN_HELP, reply_markup=admin_reply_menu())
    else:
        await msg.answer(USER_HELP, reply_markup=user_reply_menu())


@dp.message(Command("cancel"))
async def cancel_any(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    editing.pop(data.get("admin_msg_id"), None)
    await state.clear()
    await msg.answer("✖️ Действие отменено.")


# ==================== INLINE-МЕНЮ ====================

@dp.callback_query(F.data == "menu:help")
async def menu_help(cb: CallbackQuery):
    await cb.message.answer(USER_HELP)
    await cb.answer()


@dp.callback_query(F.data == "menu:about")
async def menu_about(cb: CallbackQuery):
    await cb.message.answer(USER_ABOUT)
    await cb.answer()


@dp.callback_query(F.data == "menu:rules")
async def menu_rules(cb: CallbackQuery):
    await cb.message.answer(RULES)
    await cb.answer()


@dp.callback_query(F.data == "menu:send")
async def menu_send(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Как опубликовать?", reply_markup=mode_kb())
    await cb.message.answer("⏳ Напоминаю: заявки рассматриваются <b>в течение дня</b>.")
    await state.set_state(Form.waiting_choice)
    await cb.answer()


# ==================== REPLY-МЕНЮ ЮЗЕРА ====================

@dp.message(F.text == "📤 Отправить", F.chat.id != ADMIN_CHAT_ID)
async def btn_send(msg: types.Message, state: FSMContext):
    await msg.answer("Как опубликовать?", reply_markup=mode_kb())
    await msg.answer("⏳ Напоминаю: заявки рассматриваются <b>в течение дня</b>.")
    await state.set_state(Form.waiting_choice)


@dp.message(F.text == "📜 Правила", F.chat.id != ADMIN_CHAT_ID)
async def btn_rules(msg: types.Message):
    await msg.answer(RULES)


@dp.message(F.text == "📖 Помощь", F.chat.id != ADMIN_CHAT_ID)
async def btn_help(msg: types.Message):
    await msg.answer(USER_HELP)


@dp.message(F.text == "ℹ️ О боте", F.chat.id != ADMIN_CHAT_ID)
async def btn_about(msg: types.Message):
    await msg.answer(USER_ABOUT)


# ==================== REPLY-МЕНЮ АДМИНА ====================

@dp.message(F.text == "🛠 Помощь", F.chat.id == ADMIN_CHAT_ID)
async def admin_help_btn(msg: types.Message):
    await msg.answer(ADMIN_HELP)


@dp.message(F.text == "📊 Статистика", F.chat.id == ADMIN_CHAT_ID)
async def admin_stats_btn(msg: types.Message):
    await msg.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"📥 Получено: <b>{stats['received']}</b>\n"
        f"✅ Опубликовано: <b>{stats['published']}</b>\n"
        f"❌ Отклонено: <b>{stats['rejected']}</b>"
    )


@dp.message(F.text == "📋 Последние", F.chat.id == ADMIN_CHAT_ID)
async def admin_last_btn(msg: types.Message):
    if not pending:
        await msg.answer("Нет активных предложек.")
        return
    last = list(pending.items())[-5:]
    lines = ["📋 <b>Последние предложки:</b>"]
    for uid, info in last:
        if info["anon"]:
            who = "🕶 аноним"
        elif info["username"]:
            who = f"👤 @{info['username']}"
        else:
            who = f"👤 {info['full_name']}"
        cap = (info["edited_caption"] or info["caption"] or "(без текста)")[:40]
        lines.append(f"• {who} — {cap}")
    await msg.answer("\n".join(lines))


@dp.message(Command("stats"), F.chat.id == ADMIN_CHAT_ID)
async def cmd_stats(msg: types.Message):
    await admin_stats_btn(msg)


@dp.message(Command("last"), F.chat.id == ADMIN_CHAT_ID)
async def cmd_last(msg: types.Message):
    await admin_last_btn(msg)


# ==================== ОТПРАВКА ПРЕДЛОЖКИ ====================

@dp.callback_query(F.data.startswith("mode:"), Form.waiting_choice)
async def choose_mode(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":")[1]
    await state.update_data(anon=(mode == "anon"))
    await cb.message.edit_text(
        "✅ Режим: " + ("анонимно 🕶" if mode == "anon" else "с @username 👤") +
        "\n\nТеперь отправь фото (можно с подписью)."
    )
    await cb.message.answer(
        "⏳ Напоминаю: заявки рассматриваются <b>в течение дня</b>.\n"
        "Как только админ примет решение — я пришлю уведомление."
    )
    await state.set_state(Form.waiting_photo)
    await cb.answer()


async def _send_to_admin(msg: types.Message, state: FSMContext, forwarded: bool):
    data = await state.get_data()
    anon = data.get("anon", False if forwarded else True)
    await state.clear()

    if anon:
        mark = "🕶 <b>Анонимно</b>"
    elif msg.from_user.username:
        mark = f"👤 Автор: @{msg.from_user.username}"
    else:
        mark = f"👤 Автор: {msg.from_user.full_name} (id {msg.from_user.id})"

    caption = msg.caption or ""
    admin_caption_base = mark
    if forwarded:
        admin_caption_base += "\n🔁 <i>Переслано из канала</i>"
    admin_caption = f"{admin_caption_base}\n\n{caption}" if caption else admin_caption_base

    sent = await bot.copy_message(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=msg.chat.id,
        message_id=msg.message_id,
    )
    await bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=admin_caption,
        reply_to_message_id=sent.message_id,
    )
    try:
        await bot.edit_message_reply_markup(
            chat_id=ADMIN_CHAT_ID,
            message_id=sent.message_id,
            reply_markup=build_admin_kb(sent.message_id),
        )
    except Exception:
        pass

    pending[sent.message_id] = {
        "admin_msg_id": sent.message_id,
        "anon": anon,
        "user_id": msg.from_user.id,
        "username": msg.from_user.username,
        "full_name": msg.from_user.full_name,
        "caption": caption,
        "edited_caption": None,
        "forwarded_from_channel": forwarded,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    stats["received"] += 1

    await msg.answer(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "⏳ Заявки рассматриваются <b>в течение дня</b>.\n"
        "Я пришлю уведомление, когда админ примет решение — "
        "не нужно отправлять фото повторно."
    )


@dp.message(Form.waiting_photo, F.photo)
async def handle_photo(msg: types.Message, state: FSMContext):
    await _send_to_admin(msg, state, forwarded=False)


@dp.message(Form.waiting_photo)
async def not_photo(msg: types.Message):
    await msg.answer("Пожалуйста, отправь именно <b>фото</b> 📷 (или /cancel)")


@dp.message(F.forward_origin, F.chat.type == "private", F.chat.id != ADMIN_CHAT_ID)
async def handle_forwarded(msg: types.Message, state: FSMContext):
    await _send_to_admin(msg, state, forwarded=True)


# ==================== РЕДАКТИРОВАНИЕ ПОДПИСИ ====================

@dp.callback_query(F.data.startswith("edit:"))
async def edit_caption(cb: CallbackQuery, state: FSMContext):
    msg_id = int(cb.data.split(":")[1])
    info = pending.get(msg_id)
    if not info:
        await cb.answer("Уже обработано", show_alert=True)
        return
    editing[info["admin_msg_id"]] = msg_id
    await cb.message.reply(
        "✏️ Отправь <b>новый текст подписи</b> ответом на это сообщение.\n"
        "Можно прислать <code>-</code>, чтобы очистить подпись.\n"
        "Отмена — /cancel"
    )
    await state.set_state("editing_caption")
    await state.update_data(admin_msg_id=info["admin_msg_id"])
    await cb.answer()


@dp.message(F.chat.id == ADMIN_CHAT_ID, F.text, ~F.text.startswith("/"))
async def apply_edit(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    admin_msg_id = data.get("admin_msg_id")
    if not admin_msg_id or admin_msg_id not in editing:
        return
    user_msg_id = editing.pop(admin_msg_id)
    info = pending.get(user_msg_id)
    if not info:
        await state.clear()
        await msg.answer("Предложение уже обработано.")
        return
    new_text = msg.text.strip()
    if new_text == "-":
        new_text = ""
    info["edited_caption"] = new_text
    try:
        await bot.edit_message_text(
            chat_id=ADMIN_CHAT_ID,
            message_id=info.get("caption_msg_id", admin_msg_id),
            text=build_admin_caption(info),
            reply_markup=build_admin_kb(user_msg_id, published=bool(info.get("channel_msg_id"))),
        )
    except Exception:
        await msg.answer("✅ Подпись обновлена.")
    await state.clear()
    await msg.answer(
        "✅ Подпись обновлена.\n\n"
        "Теперь можешь:\n"
        "• ✅ <b>Опубликовать</b>\n"
        "• ✏️ <b>Изменить ещё раз</b>\n"
        "• 🔄 <b>Сбросить</b>\n"
        "• 🗑 <b>Удалить</b> (если уже опубликовано)"
    )


@dp.callback_query(F.data.startswith("reset:"))
async def reset_edit(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[1])
    info = pending.get(msg_id)
    if not info:
        await cb.answer("Уже обработано", show_alert=True)
        return
    info["edited_caption"] = None
    try:
        await bot.edit_message_text(
            chat_id=ADMIN_CHAT_ID,
            message_id=info.get("caption_msg_id", info["admin_msg_id"]),
            text=build_admin_caption(info),
            reply_markup=build_admin_kb(msg_id, published=bool(info.get("channel_msg_id"))),
        )
    except Exception:
        pass
    await cb.answer("Правка сброшена 🔄")


# ==================== ПУБЛИКАЦИЯ / УДАЛЕНИЕ / ОТКЛОНЕНИЕ ====================

@dp.callback_query(F.data.startswith("pub:"))
async def publish(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[1])
    info = pending.get(msg_id)
    if not info:
        await cb.answer("Уже обработано", show_alert=True)
        return
    if info.get("channel_msg_id"):
        await cb.answer("Уже опубликовано", show_alert=True)
        return

    caption = info["edited_caption"] if info["edited_caption"] is not None else info["caption"]
    if not info["anon"] and AUTO_ADD_USERNAME:
        signature = f"\n\n👤 @{info['username']}" if info["username"] else f"\n\n👤 {info['full_name']}"
        caption = (caption or "") + signature

    sent = await bot.copy_message(
        chat_id=CHANNEL_ID,
        from_chat_id=ADMIN_CHAT_ID,
        message_id=info["admin_msg_id"],
        caption=caption or None,
    )
    info["channel_msg_id"] = sent.message_id
    stats["published"] += 1

    try:
        await bot.edit_message_reply_markup(
            chat_id=ADMIN_CHAT_ID,
            message_id=info["admin_msg_id"],
            reply_markup=build_admin_kb(msg_id, published=True),
        )
    except Exception:
        pass
    await cb.answer("Опубликовано ✅")

    try:
        await bot.send_message(info["user_id"], "✅ Твоё фото опубликовано в канале!")
    except Exception:
        pass


@dp.callback_query(F.data.startswith("del:"))
async def delete_post(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[1])
    info = pending.get(msg_id)
    if not info or not info.get("channel_msg_id"):
        await cb.answer("Пост ещё не опубликован", show_alert=True)
        return
    try:
        await bot.delete_message(chat_id=CHANNEL_ID, message_id=info["channel_msg_id"])
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return
    info["channel_msg_id"] = None
    try:
        await bot.edit_message_reply_markup(
            chat_id=ADMIN_CHAT_ID,
            message_id=info["admin_msg_id"],
            reply_markup=build_admin_kb(msg_id, published=False),
        )
    except Exception:
        pass
    await cb.answer("Удалено из канала 🗑")


@dp.callback_query(F.data.startswith("rej:"))
async def reject(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[1])
    info = pending.get(msg_id)
    if info and info.get("channel_msg_id"):
        try:
            await bot.delete_message(chat_id=CHANNEL_ID, message_id=info["channel_msg_id"])
        except Exception:
            pass
    pending.pop(msg_id, None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Отклонено")
    stats["rejected"] += 1
    if info:
        try:
            await bot.send_message(info["user_id"], "❌ Твоё фото отклонено.")
        except Exception:
            pass


# ==================== ЗАПУСК ====================

async def main():
    print("🤖 Бот запущен. Жду сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())