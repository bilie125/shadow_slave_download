import re
from docx import Document

# Заголовок главы определяется по самому тексту, а не по стилю Word.
# Это важно для файлов, где стиль называется, например, "123Заголовок".
CHAPTER_RE = re.compile(
    r"^\s*Глава\s+(\d+)\s*(?:[:—-]\s*(.*))?$",
    re.IGNORECASE,
)


def _finish_chapter(current):
    if not current:
        return None

    text = "\n".join(current.pop("parts")).strip()
    current["text"] = text
    return current


def parse_docx(path):
    """
    Разбирает DOCX по строкам вида:
        Глава 123: Название

    Стиль Word намеренно не проверяется: в исходном файле используется
    кастомный стиль "123Заголовок", а в других файлах название стиля может
    быть любым.

    Если одна и та же глава встречается дважды, сохраняется более полная
    версия. Это защищает базу от случайного дубля главы.
    """
    doc = Document(path)
    chapters_by_number = {}
    current = None

    for paragraph in doc.paragraphs:
        value = paragraph.text.strip()

        if not value:
            continue

        match = CHAPTER_RE.match(value)

        if match:
            finished = _finish_chapter(current)
            if finished:
                number = finished["number"]
                old = chapters_by_number.get(number)

                if old is None or len(finished["text"]) > len(old["text"]):
                    chapters_by_number[number] = finished

            number = int(match.group(1))
            tail = (match.group(2) or "").strip()
            title = f"Глава {number}"
            if tail:
                title += f": {tail}"

            current = {
                "number": number,
                "title": title,
                "parts": [],
            }
            continue

        if current is not None:
            current["parts"].append(value)

    finished = _finish_chapter(current)
    if finished:
        number = finished["number"]
        old = chapters_by_number.get(number)
        if old is None or len(finished["text"]) > len(old["text"]):
            chapters_by_number[number] = finished

    return [chapters_by_number[n] for n in sorted(chapters_by_number)]
