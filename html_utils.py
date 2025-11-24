# HTML 處理與萃取

from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, urlunparse

def extract_relevant_html(raw_html: str, max_length: int = 3000) -> str:
    """保留 title、部分 meta 與可見文字，供模型快速分析。"""
    soup = BeautifulSoup(raw_html, "html.parser")

    title = soup.title.string if soup.title else ""
    metas = [
        str(meta)
        for meta in soup.find_all("meta")
        if meta.get("name") in ["description", "keywords", "author"]
    ]
    links = [a.get("href") for a in soup.find_all("a", href=True)[:10]]
    body_text = soup.get_text("\n", strip=True)[:1000]

    result = (
        f"<title>{title}</title>\n"
        f"{' '.join(metas)}\n"
        f"<links>{links}</links>\n"
        f"<body>{body_text}</body>"
    )

    return result[:max_length]

# URL 正規化
def _normalize_url(url: str) -> str | None:
    """標準化 URL（過濾垃圾字元、只保留 http/https）。"""

    if not url:
        return None

    url = url.strip().strip('\'"(),.;:!?]}>')

    # 不要的協定
    if url.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None

    # 協定相對，補 http
    if url.startswith("//"):
        url = "http:" + url

    # 自動補上 http
    if url.startswith("www."):
        url = "http://" + url

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None

        netloc = parsed.netloc.lower().rstrip('.')

        # 移除預設 port
        if netloc.endswith(":80") and parsed.scheme == "http":
            netloc = netloc[:-3]
        if netloc.endswith(":443") and parsed.scheme == "https":
            netloc = netloc[:-4]

        path = parsed.path or "/"

        normalized = urlunparse((parsed.scheme, netloc, path, "", parsed.query, ""))
        return normalized

    except Exception:
        return None

# 擷取 URL
def extract_urls(text: str, max_count: int = 50) -> list[str]:
    """從 HTML 或純文字中萃取網址，並格式化。"""
    urls = set()
    lowered = text.lower()

    # HTML 模式（<a href>）
    if "<html" in lowered or "<a " in lowered or "href=" in lowered:
        try:
            soup = BeautifulSoup(text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = (a.get("href") or "").strip()
                norm = _normalize_url(href)
                if norm:
                    urls.add(norm)
        except:
            pass

    # Regex 模式（www., http://, https://）
    pattern = re.compile(r"(?i)\b((?:https?://|www\.)[^\s<>\"'\)]{3,})")
    for m in pattern.finditer(text):
        cand = m.group(1)
        norm = _normalize_url(cand)
        if norm:
            urls.add(norm)

    return sorted(urls)[:max_count]
