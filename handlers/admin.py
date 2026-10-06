import asyncio
import re
from pathlib import Path

from aiogram import Bot
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, EphemeralMessageParameters

from parsers.telegram_parser import extract_telegraph_from_message
from services.telegraph import fetch_telegraph
from services.importers import import_docx, import_links

router = Router()


def is_admin(message, admin_ids):
    return bool(message.from_user and message.from_user.id in admin_ids)


async def reply_private(message: Message, bot: Bot, text: str):
    """Ответ администратору персонально в группе, либо обычным сообщением в ЛС."""
    if message.chat.type in {"group", "supergroup"}:
        return await bot.send_message(
            chat_id=message.chat.id,
            text=text,
            ephemeral_message_parameters=EphemeralMessageParameters(
                receiver_user_id=message.from_user.id,
            ),
        )
    return await message.answer(text)


@router.message(Command("import_docx"))
async def import_docx_command(message: Message, admin_ids: set[int], bot: Bot):
    if not is_admin(message, admin_ids):
        return
    await reply_private(message, bot, "Отправь DOCX следующим сообщением.")


@router.message(Command("import_links"))
async def import_links_command(message: Message, admin_ids: set[int], bot: Bot):
    if not is_admin(message, admin_ids):
        return
    await reply_private(message, bot, "Отправь TXT-файл со ссылками в формате: Глава N: URL")


@router.message(Command("set_source_chat"))
async def set_source_chat(message: Message, db, admin_ids: set[int], bot: Bot):
    if not is_admin(message, admin_ids):
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) == 1:
        chat_id = message.chat.id
    else:
        try:
            chat_id = int(args[1].strip())
        except ValueError:
            await reply_private(message, bot, "Использование: /set_source_chat или /set_source_chat -100123456789")
            return

    await db.set_setting("source_chat_id", chat_id)
    await reply_private(message, bot, f"✅ Источник новых глав установлен: {chat_id}")


@router.message(Command("source_chat"))
async def source_chat(message: Message, db, admin_ids: set[int], bot: Bot):
    if not is_admin(message, admin_ids):
        return
    value = await db.get_setting("source_chat_id")
    await reply_private(message, bot, f"Источник: {value or 'не установлен'}")


@router.message(Command("add_volume"))
async def add_volume(message: Message, db, admin_ids: set[int], bot: Bot):
    if not is_admin(message, admin_ids):
        return
    args = (message.text or "").split()
    if len(args) != 4:
        await reply_private(message, bot, "Использование: /add_volume НОМЕР_ТОМА ГЛАВА_ОТ ГЛАВА_ДО\nПример: /add_volume 1 1 570")
        return
    try:
        number, start, end = map(int, args[1:])
    except ValueError:
        await reply_private(message, bot, "Все значения должны быть числами.")
        return
    if number < 1 or start < 1 or start > end:
        await reply_private(message, bot, "Неверные параметры тома.")
        return
    await db.upsert_volume(number, start, end)
    await reply_private(message, bot, f"✅ Том {number}: главы {start}-{end}")


@router.message(Command("delete_volume"))
async def delete_volume(message: Message, db, admin_ids: set[int], bot: Bot):
    if not is_admin(message, admin_ids):
        return
    args = (message.text or "").split()
    if len(args) != 2 or not args[1].isdigit():
        await reply_private(message, bot, "Использование: /delete_volume НОМЕР_ТОМА")
        return
    await db.delete_volume(int(args[1]))
    await reply_private(message, bot, "✅ Том удалён.")


@router.message(Command("retry_telegraph"))
async def retry_telegraph(message: Message, db, admin_ids: set[int], bot: Bot):
    if not is_admin(message, admin_ids):
        return

    rows = await db.chapters_without_text()
    if not rows:
        await reply_private(message, bot, "✅ Все сохранённые ссылки Telegraph уже имеют текст.")
        return

    await reply_private(message, bot, f"⏳ Начинаю догрузку {len(rows)} глав...")
    ok = 0
    failed = []
    for row in rows:
        try:
            data = await fetch_telegraph(row["telegraph_url"])
            if not data["text"]:
                raise RuntimeError("Пустой текст")
            await db.upsert_chapter(
                number=row["chapter_number"],
                title=data["title"] or row["title"],
                text=data["text"],
                url=row["telegraph_url"],
                source=row["source"],
                message_id=row["source_message_id"],
                chat_id=row["source_chat_id"],
            )
            ok += 1
        except Exception as exc:
            failed.append(row["chapter_number"])
            print(f"retry {row['chapter_number']}: {exc}")

    text = f"✅ Догружено: {ok}"
    if failed:
        text += f"\n❌ Не удалось: {len(failed)}\n{', '.join(map(str, failed[:50]))}"
    await reply_private(message, bot, text)


@router.message(F.document)
async def receive_document(message: Message, bot: Bot, db, admin_ids: set[int]):
    if not is_admin(message, admin_ids):
        return

    name = (message.document.file_name or "").lower()
    target_dir = Path("data/incoming")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{message.message_id}_{message.document.file_name}"

    try:
        if name.endswith(".docx"):
            await bot.download(message.document, destination=target)
            count = await import_docx(db, str(target))
            await reply_private(message, bot, f"✅ DOCX обработан. Глав добавлено/обновлено: {count}")
        elif name.endswith(".txt"):
            await bot.download(message.document, destination=target)
            imported, downloaded, errors = await import_links(db, str(target))
            text = (
                f"✅ Файл ссылок обработан.\n"
                f"Строк распознано: {imported}\n"
                f"Telegraph скачано: {downloaded}"
            )
            if errors:
                text += f"\n⚠️ Без текста: {len(errors)} — {', '.join(map(str, errors[:30]))}"
            await reply_private(message, bot, text)
    finally:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass


@router.message(
    F.is_automatic_forward,
    F.sender_chat.type == "channel",
)
async def watch_new_chapter(message: Message, db):
    """
    Обрабатывает только автоматические посты канала,
    которые Telegram пересылает в группу.

    Канал:
        message.sender_chat.type == "channel"

    Автоматическая пересылка:
        message.is_automatic_forward == True
    """

    # Игнорируем всё, что не является автоматической
    # пересылкой поста канала.
    if not message.is_automatic_forward:
        return

    # Должен быть указан источник-канал.
    if not message.sender_chat:
        return

    if message.sender_chat.type != "channel":
        return

    # Получаем ID канала.
    channel_id = message.sender_chat.id

    # Проверяем разрешённый канал.
    source_chat_id = await db.get_setting("source_chat_id")

    if source_chat_id:
        try:
            source_chat_id = int(source_chat_id)
        except (TypeError, ValueError):
            return

        if source_chat_id != channel_id:
            return

    print("\n========== CHANNEL FORWARD ==========")
    print(f"channel_id: {channel_id}")
    print(f"channel_title: {message.sender_chat.title}")
    print(f"message_id: {message.message_id}")
    print(f"text: {message.text!r}")
    print(f"entities: {message.entities!r}")
    print("=====================================")

    found = extract_telegraph_from_message(message)

    if not found:
        print("[CHANNEL] Глава/Telegraph не найдена")
        return

    chapter_number = found["number"]
    telegraph_url = found["url"]

    print(
        f"[CHANNEL] Найдена глава {chapter_number}: "
        f"{telegraph_url}"
    )

    existing = await db.get_chapter(chapter_number)

    await db.upsert_chapter(
        number=chapter_number,
        title=(
            existing["title"]
            if existing
            else f"Глава {chapter_number}"
        ),
        url=telegraph_url,
        source=(
            existing["source"]
            if existing and existing["source"] != "unknown"
            else "telegram"
        ),
        message_id=message.message_id,
        chat_id=channel_id,
    )

    if existing and existing["text"]:
        print(
            f"[CHANNEL] Глава {chapter_number} "
            f"уже есть в БД"
        )
        return

    try:
        print(
            f"[CHANNEL] Загружаю Telegraph: "
            f"{telegraph_url}"
        )

        data = await fetch_telegraph(telegraph_url)

        if not data.get("text"):
            raise RuntimeError("Telegraph вернул пустой текст")

        await db.upsert_chapter(
            number=chapter_number,
            title=data.get("title") or f"Глава {chapter_number}",
            text=data["text"],
            url=telegraph_url,
            source=(
                existing["source"]
                if existing
                else "telegram"
            ),
            message_id=message.message_id,
            chat_id=channel_id,
        )

        print(
            f"[CHANNEL] Глава {chapter_number} "
            f"успешно сохранена"
        )

    except Exception as exc:
        print(
            f"[CHANNEL] Ошибка Telegraph "
            f"{chapter_number}: {exc}"
        )
