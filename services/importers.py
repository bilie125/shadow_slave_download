from parsers.docx_parser import parse_docx
from parsers.links_parser import parse_links_file
from services.telegraph import fetch_telegraph


async def import_docx(db, path):
    chapters = parse_docx(path)
    for ch in chapters:
        await db.upsert_chapter(
            number=ch["number"],
            title=ch["title"],
            text=ch["text"],
            source="docx",
        )
    return len(chapters)


async def import_links(db, path, download_text=True):
    links = parse_links_file(path)
    imported = 0
    downloaded = 0
    errors = []

    for item in links:
        existing = await db.get_chapter(item["number"])

        if existing and existing["text"]:
            await db.upsert_chapter(
                number=item["number"],
                url=item["url"],
                source=existing["source"] or "links",
            )
            imported += 1
            continue

        title = f"Глава {item['number']}"
        text = None

        if download_text:
            try:
                data = await fetch_telegraph(item["url"])
                title = data["title"] or title
                text = data["text"]
                downloaded += 1
            except Exception as exc:
                errors.append(item["number"])
                print(f"Telegraph {item['number']}: {exc}")

        await db.upsert_chapter(
            number=item["number"],
            title=title,
            text=text,
            url=item["url"],
            source="links",
        )
        imported += 1

    return imported, downloaded, errors
