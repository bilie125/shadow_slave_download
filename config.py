import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    book_name: str
    db_path: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    raw = os.getenv("ADMIN_IDS", "")
    try:
        admin_ids = {int(x.strip()) for x in raw.split(",") if x.strip()}
    except ValueError:
        raise RuntimeError("ADMIN_IDS должен содержать только Telegram ID через запятую")

    if not admin_ids:
        raise RuntimeError("ADMIN_IDS is not set")

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        book_name=os.getenv("BOOK_NAME", "Теневой Раб"),
        db_path=os.getenv("DB_PATH", "data/book.db"),
    )
