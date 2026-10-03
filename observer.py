# ==================== OBSERVER (с поддержкой медиа) ====================
# Файл: observer.py

import os
import asyncio
import aiosqlite
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

TOKEN_OBSERVER = os.getenv("TOKEN_OBSERVER")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "/tmp/observer.db")

if not TOKEN_OBSERVER:
    raise SystemExit("❌ Не задана переменная TOKEN_OBSERVER (observer)")

observer_bot = Bot(token=TOKEN_OBSERVER, default=DefaultBotProperties(parse_mode="HTML"))
observer_dp = Dispatcher()


# ==================== БАЗА ДАННЫХ ====================

async def obs_init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS obs_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                business_connection_id TEXT,
                connected_at TEXT,
                is_banned INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS obs_connections (
                business_connection_id TEXT PRIMARY KEY,
                user_id INTEGER,
                connected_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS obs_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                chat_id INTEGER,
                sender_id INTEGER,
                sender_username TEXT,
                sender_name TEXT,
                message_id INTEGER,
                text TEXT,
                media_type TEXT,
                media_file_id TEXT,
                created_at TEXT,
                is_deleted INTEGER DEFAULT 0,
                edited_from TEXT,
                is_outgoing INTEGER DEFAULT 0
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_obs_owner ON obs_messages (owner_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_obs_msg ON obs_messages (chat_id, message_id)")
        await db.commit()


async def obs_register_user(user_id, username, full_name, connection_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO obs_users (user_id, username, full_name, business_connection_id, connected_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                business_connection_id = excluded.business_connection_id,
                connected_at = excluded.connected_at
        """, (user_id, username, full_name, connection_id,
              datetime.now().isoformat(timespec="seconds")))
        await db.execute("""
            INSERT INTO obs_connections (business_connection_id, user_id, connected_at)
            VALUES (?, ?, ?)
            ON CONFLICT(business_connection_id) DO UPDATE SET user_id = excluded.user_id
        """, (connection_id, user_id, datetime.now().isoformat(timespec="seconds")))
        await db.commit()


async def obs_get_owner(connection_id):
    if not connection_id:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM obs_connections WHERE business_connection_id = ?",
            (connection_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def obs_is_banned(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_banned FROM obs_users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return bool(row and row[0])


async def obs_save_message(owner_id, chat_id, sender_id, sender_username, sender_name,
                           message_id, text, media_type, media_file_id, is_outgoing):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO obs_messages
            (owner_id, chat_id, sender_id, sender_username, sender_name,
             message_id, text, media_type, media_file_id, created_at, is_outgoing)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            owner_id, chat_id, sender_id, sender_username, sender_name,
            message_id, text, media_type, media_file_id,
            datetime.now().isoformat(timespec="seconds"),
            1 if is_outgoing else 0
        ))
        await db.commit()


async def obs_get_message(chat_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM obs_messages WHERE chat_id = ? AND message_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id, message_id)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def obs_mark_deleted(chat_id, message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE obs_messages SET is_deleted = 1 WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id)
        )
        await db.commit()


async def obs_mark_edited(chat_id, message_id, old_text, new_text):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE obs_messages SET edited_from = ?, text = ? WHERE chat_id = ? AND message_id = ?",
            (old_text, new_text, chat_id, message_id)
        )
        await db.commit()


async def obs_recent(owner_id, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM obs_messages WHERE owner_id = ? ORDER BY id DESC LIMIT ?",
            (owner_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def obs_deleted(owner_id, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM obs_messages WHERE owner_id = ? AND is_deleted = 1 ORDER BY id DESC LIMIT ?",
            (owner_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def obs_edited(owner_id, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM obs_messages WHERE owner_id = ? AND edited_from IS NOT NULL ORDER BY id DESC LIMIT ?",
            (owner_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def obs_find(owner_id, query, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM obs_messages WHERE owner_id = ? AND text LIKE ? ORDER BY id DESC LIMIT ?",
            (owner_id, f"%{query}%", limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def obs_stats(owner_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM obs_messages WHERE owner_id = ?", (owner_id,)) as cur:
            total = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM obs_messages WHERE owner_id = ? AND is_deleted = 1", (owner_id,)) as cur:
            deleted = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM obs_messages WHERE owner_id = ? AND edited_from IS NOT NULL", (owner_id,)) as cur:
            edited = (await cur.fetchone())[0]
    return total, deleted, edited


async def obs_admin_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM obs_users") as cur:
            users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM obs_messages") as cur:
            messages = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM obs_messages WHERE is_deleted = 1") as cur:
            deleted = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM obs_messages WHERE edited_from IS NOT NULL") as cur:
            edited = (await cur.fetchone())[0]
    return users, messages, deleted, edited


async def obs_all_users(limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM obs_users ORDER BY connected_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def obs_set_ban(user_id, banned):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE obs_users SET is_banned = ? WHERE user_id = ?",
            (1 if banned else 0, user_id)
        )
        await db.commit()


async def obs_all_user_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM obs_users WHERE is_banned = 0") as cur:
            return [r[0] for r in await cur.fetchall()]


# ==================== ВСПОМОГАТЕЛЬНОЕ ====================

def obs_extract_media(message: types.Message):
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    if message.video_note:
        return "video_note", message.video_note.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.document:
        return "document", message.document.file_id
    if message.sticker:
        return "sticker", message.sticker.file_id
    if message.animation:
        return "animation", message.animation.file_id
    return "text", None


def obs_format_sender(username, name, sender_id):
    if username:
        return f"@{username}"
    if name:
        return f"{name} (id {sender_id})"
    return f"id {sender_id}"


async def obs_send_media_to(chat_id, media_type, file_id, caption=None):
    try:
        if media_type == "photo":
            await observer_bot.send_photo(chat_id, file_id, caption=caption)
        elif media_type == "video":
            await observer_bot.send_video(chat_id, file_id, caption=caption)
        elif media_type == "video_note":
            await observer_bot.send_video_note(chat_id, file_id)
            if caption:
                await observer_bot.send_message(chat_id, caption)
        elif media_type == "voice":
            await observer_bot.send_voice(chat_id, file_id, caption=caption)
        elif media_type == "audio":
            await observer_bot.send_audio(chat_id, file_id, caption=caption)
        elif media_type == "document":
            await observer_bot.send_document(chat_id, file_id, caption=caption)
        elif media_type == "sticker":
            await observer_bot.send_sticker(chat_id, file_id)
            if caption:
                await observer_bot.send_message(chat_id, caption)
        elif media_type == "animation":
            await observer_bot.send_animation(chat_id, file_id, caption=caption)
        else:
            return False
        return True
    except Exception as e:
        print(f"[observer] ошибка отправки медиа: {e}")
        return False


async def obs_send_row(chat_id, row, prefix=None):
    sender = obs_format_sender(row.get("sender_username"), row.get("sender_name"), row.get("sender_id"))
    text = row.get("text") or ""
    date = (row.get("created_at") or "")[:16].replace("T", " ")
    media_type = row.get("media_type") or "text"
    file_id = row.get("media_file_id")

    head = f"{prefix}\n" if prefix else ""
    caption_lines = [f"{head}👤 <b>{sender}</b>"]
    if text:
        caption_lines.append(f"📝 {text}")
    caption_lines.append(f"<i>{date}</i>")
    caption = "\n".join(caption_lines)

    if file_id and media_type != "text":
        ok = await obs_send_media_to(chat_id, media_type, file_id, caption=caption)
        if not ok:
            await observer_bot.send_message(chat_id, caption + f"\n(медиа: {media_type}, не удалось переслать)")
    else:
        await observer_bot.send_message(chat_id, caption)


OBS_HELP = (
    "👁 <b>Observer</b> — бот для отслеживания удалённых и изменённых сообщений.\n\n"
    "<b>Как подключить:</b>\n"
    "1. Оформи Telegram Premium (требование Telegram)\n"
    "2. Открой <b>Настройки → Telegram для бизнеса → Автоматизация чатов</b>\n"
    "3. Добавь <b>@eye_observer_bot</b>\n"
    "4. Дай все разрешения\n\n"
    "<b>Команды:</b>\n"
    "/status — статистика\n"
    "/deleted — последние удалённые\n"
    "/edited — последние изменённые\n"
    "/last 10 — последние 10 сообщений\n"
    "/find текст — поиск по архиву\n"
    "/help — эта справка"
)


# ==================== КОМАНДЫ ====================

@observer_dp.message(Command("start"))
async def obs_cmd_start(msg: types.Message):
    await msg.answer(OBS_HELP)


@observer_dp.message(Command("help"))
async def obs_cmd_help(msg: types.Message):
    await msg.answer(OBS_HELP)


@observer_dp.message(Command("status"))
async def obs_cmd_status(msg: types.Message):
    user_id = msg.from_user.id
    total, deleted, edited = await obs_stats(user_id)
    await msg.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📥 Всего сообщений: <b>{total}</b>\n"
        f"🗑 Удалено: <b>{deleted}</b>\n"
        f"✏️ Изменено: <b>{edited}</b>"
    )


@observer_dp.message(Command("deleted"))
async def obs_cmd_deleted(msg: types.Message):
    rows = await obs_deleted(msg.from_user.id, 10)
    if not rows:
        await msg.answer("Пока нет удалённых сообщений.")
        return
    await msg.answer(f"🗑 <b>Последние удалённые ({len(rows)}):</b>")
    for r in rows:
        await obs_send_row(msg.chat.id, r, prefix="🗑 Удалено")
        await asyncio.sleep(0.3)


@observer_dp.message(Command("edited"))
async def obs_cmd_edited(msg: types.Message):
    rows = await obs_edited(msg.from_user.id, 10)
    if not rows:
        await msg.answer("Пока нет изменённых сообщений.")
        return
    await msg.answer(f"✏️ <b>Последние изменённые ({len(rows)}):</b>")
    for r in rows:
        sender = obs_format_sender(r.get("sender_username"), r.get("sender_name"), r.get("sender_id"))
        cap = (
            f"✏️ <b>Изменено</b>\n"
            f"От: {sender}\n"
            f"Было: <i>{r.get('edited_from') or '—'}</i>\n"
            f"Стало: <b>{r.get('text') or '—'}</b>"
        )
        media_type = r.get("media_type") or "text"
        file_id = r.get("media_file_id")
        if file_id and media_type != "text":
            await obs_send_media_to(msg.chat.id, media_type, file_id, caption=cap)
        else:
            await observer_bot.send_message(msg.chat.id, cap)
        await asyncio.sleep(0.3)


@observer_dp.message(Command("last"))
async def obs_cmd_last(msg: types.Message):
    parts = msg.text.split(maxsplit=1)
    limit = 10
    if len(parts) > 1:
        try:
            limit = min(int(parts[1]), 20)
        except ValueError:
            pass
    rows = await obs_recent(msg.from_user.id, limit)
    if not rows:
        await msg.answer("Архив пуст.")
        return
    await msg.answer(f"📋 <b>Последние {len(rows)}:</b>")
    for r in rows:
        await obs_send_row(msg.chat.id, r)
        await asyncio.sleep(0.3)


@observer_dp.message(Command("find"))
async def obs_cmd_find(msg: types.Message):
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Использование: /find <текст>")
        return
    rows = await obs_find(msg.from_user.id, parts[1], 10)
    if not rows:
        await msg.answer("Ничего не найдено.")
        return
    await msg.answer(f"🔍 <b>Найдено {len(rows)}:</b>")
    for r in rows:
        await obs_send_row(msg.chat.id, r)
        await asyncio.sleep(0.3)


# ==================== АДМИН-КОМАНДЫ ====================

@observer_dp.message(Command("admin"))
async def obs_cmd_admin(msg: types.Message):
    if msg.from_user.id != OWNER_ID:
        return
    users, messages, deleted, edited = await obs_admin_stats()
    await msg.answer(
        f"👑 <b>Админ-статистика Observer</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📥 Всего сообщений: <b>{messages}</b>\n"
        f"🗑 Удалено: <b>{deleted}</b>\n"
        f"✏️ Изменено: <b>{edited}</b>"
    )


@observer_dp.message(Command("users"))
async def obs_cmd_users(msg: types.Message):
    if msg.from_user.id != OWNER_ID:
        return
    rows = await obs_all_users(50)
    if not rows:
        await msg.answer("Пока никто не подключился.")
        return
    lines = ["👥 <b>Пользователи:</b>\n"]
    for r in rows:
        name = r.get("full_name") or "—"
        uname = f"@{r['username']}" if r.get("username") else "—"
        ban = " 🚫" if r.get("is_banned") else ""
        date = (r.get("connected_at") or "")[:16].replace("T", " ")
        lines.append(f"• {uname} ({name}, id {r['user_id']}){ban}\n  <i>{date}</i>")
    await msg.answer("\n".join(lines)[:4000])


@observer_dp.message(Command("broadcast"))
async def obs_cmd_broadcast(msg: types.Message):
    if msg.from_user.id != OWNER_ID:
        return
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Использование: /broadcast <текст>")
        return
    text = parts[1]
    user_ids = await obs_all_user_ids()
    ok, fail = 0, 0
    for uid in user_ids:
        try:
            await observer_bot.send_message(uid, f"📢 <b>Сообщение от админа:</b>\n\n{text}")
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await msg.answer(f"✅ Отправлено: {ok}\n❌ Не дошло: {fail}")


@observer_dp.message(Command("ban"))
async def obs_cmd_ban(msg: types.Message):
    if msg.from_user.id != OWNER_ID:
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Использование: /ban <user_id>")
        return
    try:
        target = int(parts[1])
    except ValueError:
        await msg.answer("user_id должен быть числом.")
        return
    await obs_set_ban(target, True)
    await msg.answer(f"🚫 Пользователь {target} забанен.")


@observer_dp.message(Command("unban"))
async def obs_cmd_unban(msg: types.Message):
    if msg.from_user.id != OWNER_ID:
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Использование: /unban <user_id>")
        return
    try:
        target = int(parts[1])
    except ValueError:
        await msg.answer("user_id должен быть числом.")
        return
    await obs_set_ban(target, False)
    await msg.answer(f"✅ Пользователь {target} разбанен.")# ==================== BUSINESS-СОБЫТИЯ ====================

@observer_dp.business_connection()
async def obs_on_connection(connection: types.BusinessConnection):
    user = connection.user
    await obs_register_user(user.id, user.username, user.full_name, connection.id)
    try:
        await observer_bot.send_message(
            user.id,
            "✅ <b>Observer подключён!</b>\n\n"
            "Теперь я слежу за твоими личными чатами. "
            "Когда собеседник удалит или изменит сообщение — пришлю уведомление.\n\n"
            "Команды: /status, /deleted, /edited, /last, /find"
        )
    except Exception:
        pass


@observer_dp.business_message()
async def obs_on_message(message: types.Message):
    try:
        owner_id = await obs_get_owner(message.business_connection_id)
        if not owner_id:
            return
        if await obs_is_banned(owner_id):
            return

        sender = message.from_user
        media_type, media_file_id = obs_extract_media(message)

        await obs_save_message(
            owner_id=owner_id,
            chat_id=message.chat.id,
            sender_id=sender.id if sender else 0,
            sender_username=sender.username if sender else None,
            sender_name=sender.full_name if sender else None,
            message_id=message.message_id,
            text=message.text or message.caption or "",
            media_type=media_type,
            media_file_id=media_file_id,
            is_outgoing=(sender.id == owner_id) if sender else False
        )
    except Exception as e:
        print(f"[observer] ошибка в business_message: {e}")


@observer_dp.edited_business_message()
async def obs_on_edited(message: types.Message):
    try:
        owner_id = await obs_get_owner(message.business_connection_id)
        if not owner_id:
            return
        if await obs_is_banned(owner_id):
            return

        old = await obs_get_message(message.chat.id, message.message_id)
        old_text = old["text"] if old else "(неизвестно)"
        new_text = message.text or message.caption or ""

        if old_text == new_text:
            return

        await obs_mark_edited(message.chat.id, message.message_id, old_text, new_text)

        sender = message.from_user
        sender_str = obs_format_sender(
            sender.username if sender else None,
            sender.full_name if sender else None,
            sender.id if sender else 0
        )

        caption = (
            "✏️ <b>Сообщение изменено</b>\n\n"
            f"От: {sender_str}\n"
            f"<b>Было:</b> {old_text}\n"
            f"<b>Стало:</b> {new_text}"
        )

        media_type = old.get("media_type") if old else "text"
        file_id = old.get("media_file_id") if old else None

        if file_id and media_type and media_type != "text":
            await obs_send_media_to(owner_id, media_type, file_id, caption=caption)
        else:
            await observer_bot.send_message(owner_id, caption)
    except Exception as e:
        print(f"[observer] ошибка в edited_business_message: {e}")


@observer_dp.deleted_business_messages()
async def obs_on_deleted(deleted: types.BusinessMessagesDeleted):
    try:
        owner_id = await obs_get_owner(deleted.business_connection_id)
        if not owner_id:
            return
        if await obs_is_banned(owner_id):
            return

        for msg_id in deleted.message_ids:
            old = await obs_get_message(deleted.chat.id, msg_id)
            if not old:
                continue
            await obs_mark_deleted(deleted.chat.id, msg_id)

            sender_str = obs_format_sender(
                old.get("sender_username"),
                old.get("sender_name"),
                old.get("sender_id")
            )
            text = old.get("text") or ""

            caption_lines = [
                "🗑 <b>Сообщение удалено</b>",
                f"От: {sender_str}",
            ]
            if text:
                caption_lines.append(f"<b>Текст:</b> {text}")
            caption = "\n".join(caption_lines)

            media_type = old.get("media_type") or "text"
            file_id = old.get("media_file_id")

            if file_id and media_type != "text":
                await obs_send_media_to(owner_id, media_type, file_id, caption=caption)
            else:
                await observer_bot.send_message(owner_id, caption)
    except Exception as e:
        print(f"[observer] ошибка в deleted_business_messages: {e}")
    
