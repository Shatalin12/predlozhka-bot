# ==================== ПРЕДЛОЖКА ====================
# Файл: predlozhka.py
# Это отдельный модуль бота-предложки.
# Запускается из bot.py вместе с observer.

import os
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

TOKEN = os.getenv("TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
AUTO_ADD_USERNAME = True

if not TOKEN:
    raise SystemExit("❌ Не задана переменная TOKEN (предложка)")

predlozhka_bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
predlozhka_dp = Dispatcher()

p_pending = {}
p_editing = {}
p_stats = {"received": 0, "published": 0, "rejected": 0}


class PForm(StatesGroup):
    waiting_choice = State()
    waiting_content = State()


P_REVIEW_WARNING = (
    "⏳ <b>Важно:</b> заявки рассматриваются <b>в течение дня</b>.\n"
    "Пожалуйста, не отправляй одно и то же несколько раз — "
    "это не ускорит рассмотрение."
)

P_RULES = (
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

P_USER_HELP = (
    "📖 <b>Что умеет этот бот</b>\n\n"
    "Это бот-предложка для канала знакомств.\n\n"
    "<b>Как отправить заявку:</b>\n"
    "1. Жми <b>📤 Отправить</b>\n"
    "2. Выбери: <b>С @username</b> или <b>🕶 Анонимно</b>\n"
    "3. Отправь <b>фото</b> (можно с подписью) <b>или</b> просто текст\n"
    "4. Жди уведомления\n\n"
    "⏳ <b>Заявки рассматриваются в течение дня.</b>\n\n"
    "<b>Команды:</b>\n"
    "/start — начать заново\n"
    "/help — эта справка\n"
    "/cancel — отменить действие"
)

P_USER_ABOUT = (
    "ℹ️ <b>О боте</b>\n\n"
    "Бот-предложка для канала знакомств.\n"
    "Отправь фото или текст — админ рассмотрит.\n\n"
    "⏳ <b>Срок рассмотрения:</b> в течение дня."
)

P_ADMIN_HELP = (
    "🛠 <b>Меню администратора</b>\n\n"
    "<b>Кнопки на каждом сообщении:</b>\n"
    "✅ Опубликовать — уйдёт в канал\n"
    "❌ Отклонить — автору придёт отказ\n"
    "✏️ Изменить подпись\n"
    "🔄 Сбросить правку\n"
    "🗑 Удалить пост — удалить из канала\n\n"
    "<b>Команды:</b>\n"
    "/help, /cancel, /stats, /last"
)


def p_user_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📤 Отправить")],
            [KeyboardButton(text="📜 Правила"), KeyboardButton(text="📖 Помощь")],
            [KeyboardButton(text="ℹ️ О боте")],
        ],
        resize_keyboard=True,
    )


def p_admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛠 Помощь"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📋 Последние")],
        ],
        resize_keyboard=True,
    )


def p_start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Отправить предложку", callback_data="p:menu:send")],
        [
            InlineKeyboardButton(text="📜 Правила", callback_data="p:menu:rules"),
            InlineKeyboardButton(text="📖 Помощь",  callback_data="p:menu:help"),
        ],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="p:menu:about")],
    ])


def p_mode_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👤 С моим @username", callback_data="p:mode:user"),
        InlineKeyboardButton(text="🕶 Анонимно",        callback_data="p:mode:anon"),
    ]])


def p_admin_caption(info):
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


def p_admin_kb(user_msg_id, published=False):
    rows = [
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"p:pub:{user_msg_id}"),
            InlineKeyboardButton(text="❌ Отклонить",   callback_data=f"p:rej:{user_msg_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Изменить подпись", callback_data=f"p:edit:{user_msg_id}"),
            InlineKeyboardButton(text="🔄 Сбросить правку",  callback_data=f"p:reset:{user_msg_id}"),
        ],
    ]
    if published:
        rows.append([
            InlineKeyboardButton(text="🗑 Удалить пост", callback_data=f"p:del:{user_msg_id}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Команды ----------

@predlozhka_dp.message(Command("start"))
async def p_start(msg: types.Message, state: FSMContext):
    await state.clear()
    if msg.chat.id == ADMIN_CHAT_ID:
        await msg.answer(P_ADMIN_HELP, reply_markup=p_admin_menu())
        return
    await msg.answer(P_USER_HELP, reply_markup=p_user_menu())
    await msg.answer(P_REVIEW_WARNING)
    await msg.answer("Что делаем?", reply_markup=p_start_kb())


@predlozhka_dp.message(Command("help"))
async def p_help(msg: types.Message):
    if msg.chat.id == ADMIN_CHAT_ID:
        await msg.answer(P_ADMIN_HELP, reply_markup=p_admin_menu())
    else:
        await msg.answer(P_USER_HELP, reply_markup=p_user_menu())


@predlozhka_dp.message(Command("cancel"))
async def p_cancel(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    p_editing.pop(data.get("admin_msg_id"), None)
    await state.clear()
    await msg.answer("✖️ Действие отменено.")


# ---------- Inline ----------

@predlozhka_dp.callback_query(F.data == "p:menu:help")
async def p_menu_help(cb: CallbackQuery):
    await cb.message.answer(P_USER_HELP)
    await cb.answer()


@predlozhka_dp.callback_query(F.data == "p:menu:about")
async def p_menu_about(cb: CallbackQuery):
    await cb.message.answer(P_USER_ABOUT)
    await cb.answer()


@predlozhka_dp.callback_query(F.data == "p:menu:rules")
async def p_menu_rules(cb: CallbackQuery):
    await cb.message.answer(P_RULES)
    await cb.answer()


@predlozhka_dp.callback_query(F.data == "p:menu:send")
async def p_menu_send(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Как опубликовать?", reply_markup=p_mode_kb())
    await cb.message.answer("⏳ Напоминаю: заявки рассматриваются <b>в течение дня</b>.")
    await state.set_state(PForm.waiting_choice)
    await cb.answer()


# ---------- Reply-меню юзера ----------

@predlozhka_dp.message(F.text == "📤 Отправить", F.chat.id != ADMIN_CHAT_ID)
async def p_btn_send(msg: types.Message, state: FSMContext):
    await msg.answer("Как опубликовать?", reply_markup=p_mode_kb())
    await msg.answer("⏳ Напоминаю: заявки рассматриваются <b>в течение дня</b>.")
    await state.set_state(PForm.waiting_choice)


@predlozhka_dp.message(F.text == "📜 Правила", F.chat.id != ADMIN_CHAT_ID)
async def p_btn_rules(msg: types.Message):
    await msg.answer(P_RULES)


@predlozhka_dp.message(F.text == "📖 Помощь", F.chat.id != ADMIN_CHAT_ID)
async def p_btn_help(msg: types.Message):
    await msg.answer(P_USER_HELP)


@predlozhka_dp.message(F.text == "ℹ️ О боте", F.chat.id != ADMIN_CHAT_ID)
async def p_btn_about(msg: types.Message):
    await msg.answer(P_USER_ABOUT)


# ---------- Reply-меню админа ----------

@predlozhka_dp.message(F.text == "🛠 Помощь", F.chat.id == ADMIN_CHAT_ID)
async def p_adm_help(msg: types.Message):
    await msg.answer(P_ADMIN_HELP)


@predlozhka_dp.message(F.text == "📊 Статистика", F.chat.id == ADMIN_CHAT_ID)
async def p_adm_stats(msg: types.Message):
    await msg.answer(
        f"📊 <b>Статистика предложки</b>\n\n"
        f"📥 Получено: <b>{p_stats['received']}</b>\n"
        f"✅ Опубликовано: <b>{p_stats['published']}</b>\n"
        f"❌ Отклонено: <b>{p_stats['rejected']}</b>"
    )


@predlozhka_dp.message(F.text == "📋 Последние", F.chat.id == ADMIN_CHAT_ID)
async def p_adm_last(msg: types.Message):
    if not p_pending:
        await msg.answer("Нет активных предложек.")
        return
    last = list(p_pending.items())[-5:]
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


@predlozhka_dp.message(Command("stats"), F.chat.id == ADMIN_CHAT_ID)
async def p_cmd_stats(msg: types.Message):
    await p_adm_stats(msg)


@predlozhka_dp.message(Command("last"), F.chat.id == ADMIN_CHAT_ID)
async def p_cmd_last(msg: types.Message):
    await p_adm_last(msg)


# ---------- Отправка заявки ----------

@predlozhka_dp.callback_query(F.data.startswith("p:mode:"), PForm.waiting_choice)
async def p_choose_mode(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":")[2]
    await state.update_data(anon=(mode == "anon"))
    await cb.message.edit_text(
        "✅ Режим: " + ("анонимно 🕶" if mode == "anon" else "с @username 👤")
    )
    await cb.message.answer(
        "📷 Отправь <b>фото</b> (можно с подписью).\n\n"
        "<b>Совет:</b> в подписи напиши имя/псевдоним, пару слов о себе и кого ищешь.\n\n"
        "Либо отправь <b>просто текст</b>, если фото не хочешь."
    )
    await cb.message.answer("⏳ Напоминаю: заявки рассматриваются <b>в течение дня</b>.")
    await state.set_state(PForm.waiting_content)
    await cb.answer()


async def p_send_to_admin(msg: types.Message, state: FSMContext, forwarded: bool, text_only: bool = False):
    data = await state.get_data()
    anon = data.get("anon", False if forwarded else True)
    await state.clear()

    if anon:
        mark = "🕶 <b>Анонимно</b>"
    elif msg.from_user.username:
        mark = f"👤 Автор: @{msg.from_user.username}"
    else:
        mark = f"👤 Автор: {msg.from_user.full_name} (id {msg.from_user.id})"

    caption = msg.caption or msg.text or ""

    if text_only:
        mark += "\n📝 <i>Только текст</i>"
        admin_caption = f"{mark}\n\n{caption}" if caption else mark
        sent = await predlozhka_bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_caption)
        try:
            await predlozhka_bot.edit_message_reply_markup(
                chat_id=ADMIN_CHAT_ID, message_id=sent.message_id,
                reply_markup=p_admin_kb(sent.message_id),
            )
        except Exception:
            pass
        admin_msg_id = sent.message_id
    else:
        if forwarded:
            mark += "\n🔁 <i>Переслано из канала</i>"
        admin_caption = f"{mark}\n\n{caption}" if caption else mark
        sent = await predlozhka_bot.copy_message(
            chat_id=ADMIN_CHAT_ID, from_chat_id=msg.chat.id,
            message_id=msg.message_id,
        )
        await predlozhka_bot.send_message(
            chat_id=ADMIN_CHAT_ID, text=admin_caption,
            reply_to_message_id=sent.message_id,
        )
        try:
            await predlozhka_bot.edit_message_reply_markup(
                chat_id=ADMIN_CHAT_ID, message_id=sent.message_id,
                reply_markup=p_admin_kb(sent.message_id),
            )
        except Exception:
            pass
        admin_msg_id = sent.message_id

    p_pending[admin_msg_id] = {
        "admin_msg_id": admin_msg_id,
        "anon": anon,
        "user_id": msg.from_user.id,
        "username": msg.from_user.username,
        "full_name": msg.from_user.full_name,
        "caption": caption,
        "edited_caption": None,
        "forwarded_from_channel": forwarded,
        "is_text_only": text_only,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    p_stats["received"] += 1

    await msg.answer(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "⏳ Заявки рассматриваются <b>в течение дня</b>.\n"
        "Я пришлю уведомление, когда админ примет решение."
    )


@predlozhka_dp.message(PForm.waiting_content, F.photo)
async def p_handle_photo(msg: types.Message, state: FSMContext):
    await p_send_to_admin(msg, state, forwarded=False)


@predlozhka_dp.message(PForm.waiting_content, F.text)
async def p_handle_text(msg: types.Message, state: FSMContext):
    await p_send_to_admin(msg, state, forwarded=False, text_only=True)


@predlozhka_dp.message(PForm.waiting_content)
async def p_not_supported(msg: types.Message):
    await msg.answer("Отправь <b>фото</b> или <b>текст</b> 📷 (или /cancel)")


@predlozhka_dp.message(F.forward_origin, F.chat.type == "private", F.chat.id != ADMIN_CHAT_ID)
async def p_handle_forwarded(msg: types.Message, state: FSMContext):
    await p_send_to_admin(msg, state, forwarded=True)


# ---------- Редактирование подписи ----------

@predlozhka_dp.callback_query(F.data.startswith("p:edit:"))
async def p_edit_caption(cb: CallbackQuery, state: FSMContext):
    msg_id = int(cb.data.split(":")[2])
    info = p_pending.get(msg_id)
    if not info:
        await cb.answer("Уже обработано", show_alert=True)
        return
    p_editing[info["admin_msg_id"]] = msg_id
    await cb.message.reply(
        "✏️ Отправь <b>новый текст подписи</b> ответом.\n"
        "Можно прислать <code>-</code> для очистки. Отмена — /cancel"
    )
    await state.set_state("p_editing_caption")
    await state.update_data(admin_msg_id=info["admin_msg_id"])
    await cb.answer()


@predlozhka_dp.message(F.chat.id == ADMIN_CHAT_ID, F.text, ~F.text.startswith("/"))
async def p_apply_edit(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    admin_msg_id = data.get("admin_msg_id")
    if not admin_msg_id or admin_msg_id not in p_editing:
        return
    user_msg_id = p_editing.pop(admin_msg_id)
    info = p_pending.get(user_msg_id)
    if not info:
        await state.clear()
        await msg.answer("Предложение уже обработано.")
        return
    new_text = msg.text.strip()
    if new_text == "-":
        new_text = ""
    info["edited_caption"] = new_text
    try:
        if info.get("is_text_only"):
            await predlozhka_bot.edit_message_text(
                chat_id=ADMIN_CHAT_ID, message_id=info["admin_msg_id"],
                text=p_admin_caption(info),
                reply_markup=p_admin_kb(user_msg_id, published=bool(info.get("channel_msg_id"))),
            )
    except Exception:
        pass
    await state.clear()
    await msg.answer(
        "✅ Подпись обновлена.\n\n"
        "• ✅ <b>Опубликовать</b>\n"
        "• ✏️ <b>Изменить ещё раз</b>\n"
        "• 🔄 <b>Сбросить</b>\n"
        "• 🗑 <b>Удалить</b> (если уже опубликовано)"
    )


@predlozhka_dp.callback_query(F.data.startswith("p:reset:"))
async def p_reset_edit(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[2])
    info = p_pending.get(msg_id)
    if not info:
        await cb.answer("Уже обработано", show_alert=True)
        return
    info["edited_caption"] = None
    try:
        if info.get("is_text_only"):
            await predlozhka_bot.edit_message_text(
                chat_id=ADMIN_CHAT_ID, message_id=info["admin_msg_id"],
                text=p_admin_caption(info),
                reply_markup=p_admin_kb(msg_id, published=bool(info.get("channel_msg_id"))),
            )
    except Exception:
        pass
    await cb.answer("Правка сброшена 🔄")


# ---------- Публикация / удаление / отклонение ----------

@predlozhka_dp.callback_query(F.data.startswith("p:pub:"))
async def p_publish(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[2])
    info = p_pending.get(msg_id)
    if not info:
        await cb.answer("Уже обработано", show_alert=True)
        return
    if info.get("channel_msg_id"):
        await cb.answer("Уже опубликовано", show_alert=True)
        return

    caption = info["edited_caption"] if info["edited_caption"] is not None else info["caption"]
    if not info["anon"] and AUTO_ADD_USERNAME:
        sig = f"\n\n👤 @{info['username']}" if info["username"] else f"\n\n👤 {info['full_name']}"
        caption = (caption or "") + sig

    if info.get("is_text_only"):
        sent = await predlozhka_bot.send_message(chat_id=CHANNEL_ID, text=caption or "(без текста)")
    else:
        sent = await predlozhka_bot.copy_message(
            chat_id=CHANNEL_ID, from_chat_id=ADMIN_CHAT_ID,
            message_id=info["admin_msg_id"], caption=caption or None,
        )

    info["channel_msg_id"] = sent.message_id
    p_stats["published"] += 1
    try:
        await predlozhka_bot.edit_message_reply_markup(
            chat_id=ADMIN_CHAT_ID, message_id=info["admin_msg_id"],
            reply_markup=p_admin_kb(msg_id, published=True),
        )
    except Exception:
        pass
    await cb.answer("Опубликовано ✅")
    try:
        await predlozhka_bot.send_message(info["user_id"], "✅ Твоя заявка опубликована!")
    except Exception:
        pass


@predlozhka_dp.callback_query(F.data.startswith("p:del:"))
async def p_delete_post(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[2])
    info = p_pending.get(msg_id)
    if not info or not info.get("channel_msg_id"):
        await cb.answer("Пост ещё не опубликован", show_alert=True)
        return
    try:
        await predlozhka_bot.delete_message(chat_id=CHANNEL_ID, message_id=info["channel_msg_id"])
    except Exception as e:
        await cb.answer(f"Ошибка: {e}", show_alert=True)
        return
    info["channel_msg_id"] = None
    try:
        await predlozhka_bot.edit_message_reply_markup(
            chat_id=ADMIN_CHAT_ID, message_id=info["admin_msg_id"],
            reply_markup=p_admin_kb(msg_id, published=False),
        )
    except Exception:
        pass
    await cb.answer("Удалено 🗑")


@predlozhka_dp.callback_query(F.data.startswith("p:rej:"))
async def p_reject(cb: CallbackQuery):
    msg_id = int(cb.data.split(":")[2])
    info = p_pending.get(msg_id)
    if info and info.get("channel_msg_id"):
        try:
            await predlozhka_bot.delete_message(chat_id=CHANNEL_ID, message_id=info["channel_msg_id"])
        except Exception:
            pass
    p_pending.pop(msg_id, None)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.answer("Отклонено")
    p_stats["rejected"] += 1
    if info:
        try:
            await predlozhka_bot.send_message(info["user_id"], "❌ Твоя заявка отклонена.")
        except Exception:
            pass