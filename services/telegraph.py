import re
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

API_URL = "https://api.telegra.ph/getPage/{path}"


def _path_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in {"telegra.ph", "www.telegra.ph"}:
        raise ValueError(f"Не Telegraph URL: {url}")
    path = parsed.path.strip("/")
    if not path:
        raise ValueError(f"Пустой путь Telegraph: {url}")
    return path


def _nodes_to_text(nodes):
    blocks = []

    def inline(node):
        if isinstance(node, str):
            return node
        if not isinstance(node, dict):
            return ""
        return "".join(inline(child) for child in node.get("children", []))

    def walk(node):
        if isinstance(node, str):
            return
        if not isinstance(node, dict):
            return

        tag = node.get("tag", "").lower()
        children = node.get("children", [])

        if tag in {"p", "h3", "h4", "blockquote", "pre"}:
            value = inline(node).strip()
            if value:
                blocks.append(value)
            return

        if tag == "br":
            blocks.append("")
            return

        if tag in {"ul", "ol"}:
            for child in children:
                if isinstance(child, dict) and child.get("tag") == "li":
                    value = inline(child).strip()
                    if value:
                        blocks.append(value)
            return

        if tag in {"img", "figure", "figcaption", "iframe", "video", "hr"}:
            # Мультимедиа и служебные элементы в файл главы не попадают.
            return

        for child in children:
            walk(child)

    for node in nodes or []:
        walk(node)

    result = []
    previous_blank = False
    for item in blocks:
        item = re.sub(r"[ \t]+", " ", item).strip()
        if not item:
            if not previous_blank:
                result.append("")
            previous_blank = True
            continue
        result.append(item)
        previous_blank = False

    return "\n\n".join(result).strip()


async def _fetch_api(url):
    path = _path_from_url(url)
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": "ShadowSlaveBot/1.0"}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(API_URL.format(path=path), params={"return_content": "true"}) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)

    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Telegraph API error"))

    page = data.get("result", {})
    text = _nodes_to_text(page.get("content", []))
    return {
        "title": (page.get("title") or "").strip(),
        "text": text,
    }


async def _fetch_html(url):
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ShadowSlaveBot/1.0)"}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("#article") or soup.find("article")
    if article is None:
        raise RuntimeError("Не найден основной текст Telegraph")

    for tag in article.find_all(["script", "style", "img", "iframe", "video", "audio"]):
        tag.decompose()

    parts = []
    for node in article.find_all(["p", "h3", "h4", "blockquote"]):
        value = node.get_text(" ", strip=True)
        if value:
            parts.append(value)

    title = ""
    h1 = article.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)

    return {"title": title, "text": "\n\n".join(parts).strip()}


async def fetch_telegraph(url):
    """Получает только содержимое статьи, без интерфейса Telegraph."""
    try:
        result = await _fetch_api(url)
        if result["text"]:
            return result
    except Exception:
        # HTML fallback нужен для совместимости с нестандартными страницами.
        pass

    return await _fetch_html(url)
