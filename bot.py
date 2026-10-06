import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from config import load_config
from database import Database
from handlers import admin, user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def setup_commands(bot: Bot):
    # В группах пользовательские команды невидимы для остальных участников.
    await bot.set_my_commands(
        [
            BotCommand(
                command="start",
                description="Открыть меню",
                is_ephemeral=True,
            ),
            BotCommand(
                command="chapters",
                description="Скачать диапазон глав",
                is_ephemeral=True,
            ),
            BotCommand(
                command="volumes",
                description="Выбрать том",
                is_ephemeral=True,
            ),
            BotCommand(
                command="status",
                description="Состояние базы",
                is_ephemeral=True,
            ),
            BotCommand(
                command="import_docx",
                description="Импортировать DOCX",
                is_ephemeral=True,
            ),
            BotCommand(
                command="import_links",
                description="Импортировать TXT со ссылками",
                is_ephemeral=True,
            ),
            BotCommand(
                command="set_source_chat",
                description="Установить чат источника",
                is_ephemeral=True,
            ),
            BotCommand(
                command="source_chat",
                description="Показать чат источника",
                is_ephemeral=True,
            ),
            BotCommand(
                command="add_volume",
                description="Создать/изменить том",
                is_ephemeral=True,
            ),
            BotCommand(
                command="delete_volume",
                description="Удалить том",
                is_ephemeral=True,
            ),
            BotCommand(
                command="retry_telegraph",
                description="Догрузить главы Telegraph",
                is_ephemeral=True,
            ),
        ],
        scope=BotCommandScopeAllGroupChats(),
    )

    # В личном чате команды обычные.
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть меню"),
            BotCommand(command="chapters", description="Скачать диапазон глав"),
            BotCommand(command="volumes", description="Выбрать том"),
            BotCommand(command="status", description="Состояние базы"),
            BotCommand(command="import_docx", description="Импортировать DOCX"),
            BotCommand(command="import_links", description="Импортировать TXT со ссылками"),
            BotCommand(command="set_source_chat", description="Установить чат источника"),
            BotCommand(command="source_chat", description="Показать чат источника"),
            BotCommand(command="add_volume", description="Создать/изменить том"),
            BotCommand(command="delete_volume", description="Удалить том"),
            BotCommand(command="retry_telegraph", description="Догрузить главы Telegraph"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )


async def main():
    config = load_config()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(config.bot_token)
    dp = Dispatcher()

    dp.include_router(admin.router)
    dp.include_router(user.router)

    try:
        await setup_commands(bot)
        logging.getLogger(__name__).info("Ephemeral commands configured")
        await dp.start_polling(
            bot,
            db=db,
            admin_ids=config.admin_ids,
            book_name=config.book_name,
        )
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
