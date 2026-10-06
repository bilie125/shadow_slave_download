import tempfile
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
    EphemeralMessageParameters,
)

from services.generators import generate_file

router = Router()
_generation_users: set[int] = set()


def _format_kb(prefix: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 TXT", callback_data=f"fmt:{prefix}:txt"),
            InlineKeyboardButton(text="📝 DOCX", callback_data=f"fmt:{prefix}:docx"),
            InlineKeyboardButton(text="📱 EPUB", callback_data=f"fmt:{prefix}:epub"),
        ]
    ])


def _range_key(start, end):
    return f"r:{start}:{end}"


def _is_group(message: Message) -> bool:
    return message.chat.type in {"group", "supergroup"}


async def _send_ephemeral_or_regular(
    bot: Bot,
    chat_id: int,
    user_id: int,
    text: str,
    *,
    reply_markup=None,
):
    """Отправляет персональное сообщение в группе или обычное в ЛС."""
    chat = await bot.get_chat(chat_id)
    if chat.type in {"group", "supergroup"}:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            ephemeral_message_parameters=EphemeralMessageParameters(
                receiver_user_id=user_id,
            ),
        )

    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
    )


async def _edit_private_or_ephemeral(callback: CallbackQuery, text: str, reply_markup=None):
    message = callback.message
    if not message:
        return

    if message.ephemeral_message_id is not None:
        await callback.bot.edit_ephemeral_message_text(
            chat_id=message.chat.id,
            receiver_user_id=callback.from_user.id,
            ephemeral_message_id=message.ephemeral_message_id,
            text=text,
            reply_markup=reply_markup,
        )
    else:
        await message.edit_text(text, reply_markup=reply_markup)


async def _send_document_private_or_ephemeral(
    bot: Bot,
    chat_id: int,
    user_id: int,
    path: Path,
    caption: str,
):
    chat = await bot.get_chat(chat_id)
    if chat.type in {"group", "supergroup"}:
        return await bot.send_document(
            chat_id=chat_id,
            document=FSInputFile(path),
            caption=caption,
            ephemeral_message_parameters=EphemeralMessageParameters(
                receiver_user_id=user_id,
            ),
        )

    return await bot.send_document(
        chat_id=chat_id,
        document=FSInputFile(path),
        caption=caption,
    )


async def _range_state(db, start, end):
    missing = await db.missing_range(start, end)
    rows = await db.get_chapters_range(start, end)
    no_text = [
        r["chapter_number"]
        for r in rows
        if not (r["text"] or "").strip()
    ]
    missing_all = sorted(set(missing) | set(no_text))
    return rows, missing_all


def _missing_text(start, end, missing_all):
    preview = ", ".join(map(str, missing_all[:30]))
    if len(missing_all) > 30:
        preview += f" … и ещё {len(missing_all) - 30}"
    return (
        f"⚠️ Диапазон {start}-{end} пока неполный.\n"
        f"Отсутствуют/без текста: {preview}\n\n"
        "Сначала дождитесь догрузки глав или проверьте их ссылки."
    )


@router.message(Command("start"))
async def start(message: Message, bot: Bot):
    text = (
        "📚 Теневой Раб\n\n"
        "/chapters 3000-3177 — скачать диапазон\n"
        "/status — состояние базы"
    )
    await _send_ephemeral_or_regular(bot, message.chat.id, message.from_user.id, text)


@router.message(Command("status"))
async def status(message: Message, db, bot: Bot):
    total = await db.count_chapters()
    ready = await db.count_with_text()
    await _send_ephemeral_or_regular(
        bot,
        message.chat.id,
        message.from_user.id,
        f"📚 Глав в базе: {total}\n",
    )


@router.message(Command("chapters"))
async def chapters_command(message: Message, db, bot: Bot):
    user_id = message.from_user.id
    chat_id = message.chat.id
    args = (message.text or "").split(maxsplit=1)
    if len(args) != 2:
        await _send_ephemeral_or_regular(bot, chat_id, user_id, "Использование: /chapters 3000-3177")
        return

    raw = args[1].replace("—", "-").replace("–", "-").strip()
    try:
        start, end = [int(x.strip()) for x in raw.split("-", 1)]
    except ValueError:
        await _send_ephemeral_or_regular(bot, chat_id, user_id, "Формат: /chapters 3000-3177")
        return

    if start > end or start < 1:
        await _send_ephemeral_or_regular(bot, chat_id, user_id, "Неверный диапазон глав.")
        return
    if end - start + 1 > 500:
        await _send_ephemeral_or_regular(bot, chat_id, user_id, "За один файл можно запросить максимум 500 глав.")
        return

    _, missing_all = await _range_state(db, start, end)
    if missing_all:
        await _send_ephemeral_or_regular(
            bot,
            chat_id,
            user_id,
            _missing_text(start, end, missing_all),
        )
        return

    await _send_ephemeral_or_regular(
        bot,
        chat_id,
        user_id,
        f"📚 Главы {start}-{end} готовы.\n\nВыберите формат:",
        reply_markup=_format_kb(_range_key(start, end)),
    )


@router.message(Command("volumes"))
async def volumes_command(message: Message, db, bot: Bot):
    volumes = await db.list_volumes()
    if not volumes:
        await _send_ephemeral_or_regular(
            bot, message.chat.id, message.from_user.id, "Тома пока не настроены."
        )
        return

    rows = []
    for v in volumes:
        rows.append([
            InlineKeyboardButton(
                text=f"Том {v['volume_number']} ({v['start_chapter']}-{v['end_chapter']})",
                callback_data=f"volume:{v['volume_number']}",
            )
        ])

    await _send_ephemeral_or_regular(
        bot,
        message.chat.id,
        message.from_user.id,
        "📚 Выберите том:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("volume:"))
async def volume_callback(callback: CallbackQuery, db):
    try:
        number = int(callback.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer("Некорректный номер тома", show_alert=True)
        return

    volume = await db.get_volume(number)
    if not volume:
        await callback.answer("Том не найден", show_alert=True)
        return

    start = volume["start_chapter"]
    end = volume["end_chapter"]
    _, missing_all = await _range_state(db, start, end)
    if missing_all:
        await callback.answer("В томе ещё есть главы без текста.", show_alert=True)
        await _edit_private_or_ephemeral(
            callback,
            _missing_text(start, end, missing_all),
        )
        return

    await _edit_private_or_ephemeral(
        callback,
        f"📚 Том {number}: главы {start}-{end}\n\nВыберите формат:",
        _format_kb(_range_key(start, end)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fmt:r:"))
async def format_callback(callback: CallbackQuery, db, book_name: str):
    parts = callback.data.split(":")
    if len(parts) != 5:
        await callback.answer("Некорректный запрос", show_alert=True)
        return

    try:
        start = int(parts[2])
        end = int(parts[3])
    except ValueError:
        await callback.answer("Некорректный диапазон", show_alert=True)
        return

    fmt = parts[4].lower()
    if fmt not in {"txt", "docx", "epub"}:
        await callback.answer("Неизвестный формат", show_alert=True)
        return

    await _send_range(callback, db, start, end, fmt, book_name)


async def _send_range(callback, db, start, end, fmt, book_name):
    user_id = callback.from_user.id
    if user_id in _generation_users:
        await callback.answer("⏳ Для тебя уже готовится файл.", show_alert=True)
        return

    rows, missing_all = await _range_state(db, start, end)
    if missing_all:
        await callback.answer("Диапазон больше не полный.", show_alert=True)
        await _edit_private_or_ephemeral(
            callback,
            _missing_text(start, end, missing_all),
        )
        return

    _generation_users.add(user_id)
    await callback.answer("⏳ Начинаю создание файла...")

    fmt_name = {"txt": "TXT", "docx": "DOCX", "epub": "EPUB"}[fmt]
    await _edit_private_or_ephemeral(
        callback,
        f"⏳ Формирую книгу...\n\n"
        f"📚 Главы: {start}-{end}\n"
        f"📄 Формат: {fmt_name}",
    )

    suffix = "." + fmt
    filename = f"{book_name} {start}-{end}{suffix}"
    temp_dir = Path(tempfile.gettempdir()) / "shadow_slave_bot"
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / filename

    try:
        await generate_file(rows, fmt, path, book_name)
        await _send_document_private_or_ephemeral(
            callback.bot,
            callback.message.chat.id,
            user_id,
            path,
            f"📚 {book_name}, главы {start}-{end}",
        )
        try:
            await _edit_private_or_ephemeral(
                callback,
                f"✅ Готово!\n\n📚 Главы: {start}-{end}\n📄 Формат: {fmt_name}",
            )
        except Exception:
            # Ephemeral-сообщение могло уже исчезнуть. Сам файл уже отправлен.
            pass
    except Exception as exc:
        await _edit_private_or_ephemeral(
            callback,
            f"❌ Ошибка создания файла:\n{exc}",
        )
    finally:
        _generation_users.discard(user_id)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
