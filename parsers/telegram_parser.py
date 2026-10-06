import re


CHAPTER_RE = re.compile(
    r"Глава\s+(\d+)\b",
    re.IGNORECASE,
)

TELEGRAPH_RE = re.compile(
    r"^https?://telegra\.ph/",
    re.IGNORECASE,
)


def extract_telegraph_from_message(message):
    text = message.text or ""

    if not text:
        return None

    chapter_match = CHAPTER_RE.search(text)

    if not chapter_match:
        return None

    chapter_number = int(chapter_match.group(1))

    entities = message.entities or []

    for entity in entities:
        if entity.type != "text_link":
            continue

        if not entity.url:
            continue

        if not TELEGRAPH_RE.match(entity.url):
            continue

        return {
            "number": chapter_number,
            "url": entity.url,
        }

    return None