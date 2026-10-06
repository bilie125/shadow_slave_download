import asyncio
import re
import zipfile
import hashlib
from pathlib import Path
from html import escape

from ebooklib import epub


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def _safe_filename(value: str) -> str:
    value = re.sub(
        r"[^\w\-. ]+",
        "_",
        value,
        flags=re.UNICODE
    ).strip()

    return value[:120] or "book"


def _chapter_title(row):
    title = (row["title"] or "").strip()

    if title:
        return title

    return f"Глава {row['chapter_number']}"


def _chapter_text(row):
    return (row["text"] or "").strip()


def _clean_paragraphs(text):
    """
    Разбивает текст главы на абзацы.

    Пустые строки удаляются.
    """
    if not text:
        return []

    result = []

    for paragraph in text.splitlines():
        paragraph = paragraph.strip()

        if paragraph:
            result.append(paragraph)

    return result


# ============================================================
# TXT
# ============================================================

def _build_plain(chapters):
    parts = []

    for row in chapters:
        title = _chapter_title(row)

        paragraphs = _clean_paragraphs(
            _chapter_text(row)
        )

        parts.append(title)

        if paragraphs:
            parts.append(
                "\n\n".join(paragraphs)
            )

    return "\n\n".join(parts).strip() + "\n"


def generate_txt(chapters, path):
    Path(path).write_text(
        _build_plain(chapters),
        encoding="utf-8"
    )


# ============================================================
# DOCX
# ============================================================

CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">

    <Default
        Extension="rels"
        ContentType="application/vnd.openxmlformats-package.relationships+xml"/>

    <Default
        Extension="xml"
        ContentType="application/xml"/>

    <Override
        PartName="/word/document.xml"
        ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>

    <Override
        PartName="/word/styles.xml"
        ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>

    <Override
        PartName="/word/settings.xml"
        ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>

</Types>
"""


RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships
    xmlns="http://schemas.openxmlformats.org/package/2006/relationships">

    <Relationship
        Id="rId1"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
        Target="word/document.xml"/>

</Relationships>
"""


DOCUMENT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships
    xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>
"""


SETTINGS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>

<w:settings
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">

    <w:zoom w:percent="100"/>

    <w:compat>

        <w:compatSetting
            w:name="compatibilityMode"
            w:uri="http://schemas.microsoft.com/office/word"
            w:val="15"/>

    </w:compat>

</w:settings>
"""


# ============================================================
# СТИЛИ WORD
# ============================================================

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>

<w:styles
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">

    <!-- ================================================= -->
    <!-- НАСТРОЙКИ ПО УМОЛЧАНИЮ                            -->
    <!-- ================================================= -->

    <w:docDefaults>

        <w:rPrDefault>

            <w:rPr>

                <w:rFonts
                    w:ascii="Arial"
                    w:hAnsi="Arial"
                    w:eastAsia="Arial"
                    w:cs="Arial"/>

                <w:sz w:val="22"/>
                <w:szCs w:val="22"/>

            </w:rPr>

        </w:rPrDefault>


        <w:pPrDefault>

            <w:pPr>

                <w:spacing
                    w:after="120"
                    w:line="276"
                    w:lineRule="auto"/>

            </w:pPr>

        </w:pPrDefault>

    </w:docDefaults>


    <!-- ================================================= -->
    <!-- ОБЫЧНЫЙ ТЕКСТ                                    -->
    <!-- ================================================= -->

    <w:style
        w:type="paragraph"
        w:default="1"
        w:styleId="Normal">

        <w:name w:val="Normal"/>

        <w:rPr>

            <w:rFonts
                w:ascii="Arial"
                w:hAnsi="Arial"
                w:eastAsia="Arial"
                w:cs="Arial"/>

            <w:sz w:val="22"/>
            <w:szCs w:val="22"/>

        </w:rPr>

    </w:style>


    <!-- ================================================= -->
    <!-- НАСТОЯЩИЙ HEADING 1                              -->
    <!-- ================================================= -->

    <w:style
        w:type="paragraph"
        w:styleId="Heading1">

        <!-- Название стиля для Word -->
        <w:name w:val="heading 1"/>

        <!-- Основа -->
        <w:basedOn w:val="Normal"/>

        <!-- Следующий абзац -->
        <w:next w:val="Normal"/>

        <!-- Сделать стиль доступным как основной -->
        <w:qFormat/>

        <w:pPr>

            <!-- Не отделять заголовок от текста -->
            <w:keepNext/>

            <!-- ================================================= -->
            <!-- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ                              -->
            <!-- 0 = уровень Heading 1                          -->
            <!-- ================================================= -->

            <w:outlineLvl w:val="0"/>

            <!-- Интервалы -->
            <w:spacing
                w:before="240"
                w:after="240"/>

            <!-- Центрирование -->
            <w:jc w:val="center"/>

        </w:pPr>


        <w:rPr>

            <w:rFonts
                w:ascii="Arial"
                w:hAnsi="Arial"
                w:eastAsia="Arial"
                w:cs="Arial"/>

            <!-- Жирный -->
            <w:b/>
            <w:bCs/>

            <!-- 14 pt -->
            <w:sz w:val="28"/>
            <w:szCs w:val="28"/>

        </w:rPr>

    </w:style>

</w:styles>
"""


# ============================================================
# XML
# ============================================================

def _xml_text(text):
    return escape(
        text,
        quote=False
    )


# ============================================================
# ОБЫЧНЫЙ ТЕКСТОВЫЙ RUN
# ============================================================

def _docx_run(text):
    return (
        '<w:r>'

        '<w:rPr>'

        '<w:rFonts '
        'w:ascii="Arial" '
        'w:hAnsi="Arial" '
        'w:eastAsia="Arial" '
        'w:cs="Arial"/>'

        '<w:sz w:val="22"/>'
        '<w:szCs w:val="22"/>'

        '</w:rPr>'

        f'<w:t xml:space="preserve">'
        f'{_xml_text(text)}'
        f'</w:t>'

        '</w:r>'
    )


# ============================================================
# ЗАГОЛОВОК ГЛАВЫ
# ============================================================

def _docx_heading(text):
    """
    Создаёт настоящий Heading 1 для Word.

    Используются одновременно:

    1. w:pStyle = Heading1
    2. w:outlineLvl = 0

    Благодаря этому Word должен распознавать абзац
    как заголовок первого уровня.
    """

    return (
        '<w:p>'

        '<w:pPr>'

        # ====================================================
        # СТИЛЬ HEADING 1
        # ====================================================

        '<w:pStyle w:val="Heading1"/>'


        # ====================================================
        # УРОВЕНЬ СТРУКТУРЫ WORD
        #
        # 0 = Heading 1
        # 1 = Heading 2
        # 2 = Heading 3
        # ====================================================

        '<w:outlineLvl w:val="0"/>'


        # ====================================================
        # ВЫРАВНИВАНИЕ
        # ====================================================

        '<w:jc w:val="center"/>'


        # ====================================================
        # ОТСТУПЫ
        # ====================================================

        '<w:spacing '
        'w:before="240" '
        'w:after="240"/>'


        # ====================================================
        # НЕ ОТДЕЛЯТЬ ОТ СЛЕДУЮЩЕГО АБЗАЦА
        # ====================================================

        '<w:keepNext/>'

        '</w:pPr>'


        # ====================================================
        # ТЕКСТ ЗАГОЛОВКА
        # ====================================================

        '<w:r>'

        '<w:rPr>'

        # Шрифт
        '<w:rFonts '
        'w:ascii="Arial" '
        'w:hAnsi="Arial" '
        'w:eastAsia="Arial" '
        'w:cs="Arial"/>'


        # Жирный
        '<w:b/>'
        '<w:bCs/>'


        # 14 pt
        '<w:sz w:val="28"/>'
        '<w:szCs w:val="28"/>'

        '</w:rPr>'


        f'<w:t xml:space="preserve">'
        f'{_xml_text(text)}'
        f'</w:t>'

        '</w:r>'

        '</w:p>'
    )


# ============================================================
# ОБЫЧНЫЙ АБЗАЦ
# ============================================================

def _docx_paragraph(text):
    return (
        '<w:p>'

        '<w:pPr>'

        '<w:spacing '
        'w:after="120" '
        'w:line="276" '
        'w:lineRule="auto"/>'

        # Красная строка
        '<w:ind w:firstLine="400"/>'

        '</w:pPr>'

        f'{_docx_run(text)}'

        '</w:p>'
    )


# ============================================================
# РАЗРЫВ СТРАНИЦЫ
# ============================================================

def _docx_page_break():
    return (
        '<w:p>'

        '<w:r>'

        '<w:br w:type="page"/>'

        '</w:r>'

        '</w:p>'
    )


# ============================================================
# СОЗДАНИЕ DOCUMENT.XML
# ============================================================

def _build_document_xml(chapters):

    parts = []

    parts.append(
        '<?xml version="1.0" '
        'encoding="UTF-8" '
        'standalone="yes"?>'
    )

    parts.append(
        '<w:document '
        'xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
    )

    parts.append(
        '<w:body>'
    )


    # ========================================================
    # ГЛАВЫ
    # ========================================================

    for index, row in enumerate(chapters):

        # Каждая глава с новой страницы
        if index > 0:

            parts.append(
                _docx_page_break()
            )


        # ----------------------------------------------------
        # Заголовок
        # ----------------------------------------------------

        title = _chapter_title(row)

        parts.append(
            _docx_heading(title)
        )


        # ----------------------------------------------------
        # Текст
        # ----------------------------------------------------

        paragraphs = _clean_paragraphs(
            _chapter_text(row)
        )

        for paragraph in paragraphs:

            parts.append(
                _docx_paragraph(paragraph)
            )


    # ========================================================
    # ПАРАМЕТРЫ СТРАНИЦЫ
    # ========================================================

    parts.append(
        """
        <w:sectPr>

            <w:pgSz
                w:w="11906"
                w:h="16838"/>

            <w:pgMar
                w:top="1134"
                w:right="1134"
                w:bottom="1134"
                w:left="1134"
                w:header="708"
                w:footer="708"
                w:gutter="0"/>

        </w:sectPr>
        """
    )


    parts.append(
        '</w:body>'
    )

    parts.append(
        '</w:document>'
    )


    return "".join(parts)


# ============================================================
# ГЕНЕРАЦИЯ DOCX
# ============================================================

def generate_docx(
    chapters,
    path,
    book_name="Теневой Раб"
):
    """
    Быстрая генерация DOCX.

    Используется прямое создание OOXML,
    без python-docx.
    """

    # Создаём document.xml
    document_xml = _build_document_xml(
        chapters
    )


    path = Path(path)


    # DOCX = ZIP с XML-файлами
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1
    ) as docx:

        docx.writestr(
            "[Content_Types].xml",
            CONTENT_TYPES_XML
        )

        docx.writestr(
            "_rels/.rels",
            RELS_XML
        )

        docx.writestr(
            "word/document.xml",
            document_xml
        )

        docx.writestr(
            "word/styles.xml",
            STYLES_XML
        )

        docx.writestr(
            "word/settings.xml",
            SETTINGS_XML
        )

        docx.writestr(
            "word/_rels/document.xml.rels",
            DOCUMENT_RELS_XML
        )


# ============================================================
# EPUB
# ============================================================

def generate_epub(
    chapters,
    path,
    book_name="Теневой Раб"
):

    book = epub.EpubBook()


    # Уникальный ID книги
    chapter_numbers = tuple(
        str(row["chapter_number"])
        for row in chapters
    )

    book_id = hashlib.sha1(
        ",".join(chapter_numbers).encode("utf-8")
    ).hexdigest()

    book.set_identifier(
        "book-" + book_id
    )

    book.set_title(
        book_name
    )

    book.set_language(
        "ru"
    )


    spine = ["nav"]
    toc = []


    for row in chapters:

        chapter_no = row["chapter_number"]

        title = _chapter_title(row)

        paragraphs = _clean_paragraphs(
            _chapter_text(row)
        )


        html_parts = [
            f"<h1>{escape(title, quote=False)}</h1>"
        ]


        for paragraph in paragraphs:

            html_parts.append(
                f"<p>{escape(paragraph, quote=False)}</p>"
            )


        html = "".join(
            html_parts
        )


        item = epub.EpubHtml(
            title=title,
            file_name=f"chapter_{chapter_no}.xhtml",
            lang="ru"
        )


        item.content = f"""
<html>

<head>

    <meta charset="utf-8">

    <style>

        body {{
            font-family: serif;
            line-height: 1.4;
            margin: 5%;
        }}

        h1 {{
            text-align: center;
            margin-bottom: 2em;
        }}

        p {{
            text-indent: 1.5em;
            margin-top: 0;
            margin-bottom: 0.8em;
        }}

    </style>

</head>

<body>

{html}

</body>

</html>
"""


        book.add_item(
            item
        )

        spine.append(
            item
        )

        toc.append(
            item
        )


    book.toc = tuple(
        toc
    )


    book.add_item(
        epub.EpubNcx()
    )

    book.add_item(
        epub.EpubNav()
    )


    book.spine = spine


    epub.write_epub(
        path,
        book
    )


# ============================================================
# ОБЩАЯ ФУНКЦИЯ
# ============================================================

async def generate_file(
    chapters,
    fmt,
    path,
    book_name
):

    loop = asyncio.get_running_loop()

    start_time = loop.time()


    print(
        f"[GEN] Начало генерации: "
        f"format={fmt}, "
        f"chapters={len(chapters)}"
    )


    # ========================================================
    # TXT
    # ========================================================

    if fmt == "txt":

        await asyncio.to_thread(
            generate_txt,
            chapters,
            path
        )


    # ========================================================
    # DOCX
    # ========================================================

    elif fmt == "docx":

        await asyncio.to_thread(
            generate_docx,
            chapters,
            path,
            book_name
        )


    # ========================================================
    # EPUB
    # ========================================================

    elif fmt == "epub":

        await asyncio.to_thread(
            generate_epub,
            chapters,
            path,
            book_name
        )


    else:

        raise ValueError(
            f"Неизвестный формат: {fmt}"
        )


    elapsed = (
        loop.time() - start_time
    )


    print(
        f"[GEN] Генерация завершена: "
        f"format={fmt}, "
        f"time={elapsed:.2f} сек, "
        f"path={path}"
    )

