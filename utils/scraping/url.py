from bs4 import BeautifulSoup
from urllib.parse import urlparse,urljoin
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

TRUSTED_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".gif"}

def absolute_url(base_url, path):
    if not path or not isinstance(path, str):
        return None
    return urljoin(base_url, path)

def is_url_accessible(url: str, referer: str = "") -> bool:
    if not url or url.startswith("data:"):
        return True
    
    # Trust same-domain URLs with known image extensions — avoid false negatives
    # from hotlink protection, bot detection, or cookie walls
    parsed_url = urlparse(url)
    parsed_ref = urlparse(referer) if referer else None
    ext = "." + url.rsplit(".", 1)[-1].split("?")[0].lower() if "." in url else ""
    
    if parsed_ref and parsed_url.netloc == parsed_ref.netloc and ext in TRUSTED_EXTENSIONS:
        return True  # same-domain image — trust it, let download_logo handle failures

    try:
        headers = {**HEADERS}
        if referer:
            headers["Referer"] = referer
        resp = requests.get(url, headers=headers, timeout=10, allow_redirects=True, stream=True)
        resp.close()
        return resp.status_code in (200, 206, 304, 406)
    except Exception:
        return False
    
def resolve_final_url(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5, allow_redirects=True)
        final = resp.url
        parsed = urlparse(final)
        if (parsed.scheme == "https" and parsed.port == 443) or (parsed.scheme
            == "http" and parsed.port == 80):
            final = parsed._replace(netloc=parsed.hostname).geturl()
        if final != url:
            print(f"  Resolved {url} -> {final}")
        return final
    except Exception:
        return url

INVALID_CANONICAL_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "::1",
}

def extract_canonical_url(soup: BeautifulSoup, base_url: str) -> str | None:
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        resolved = absolute_url(base_url, canonical["href"])
        parsed = urlparse(resolved)
        if parsed.hostname in INVALID_CANONICAL_HOSTS:
            return None
        if parsed.hostname and (
            parsed.hostname.startswith("192.168.") or
            parsed.hostname.startswith("10.") or
            parsed.hostname.startswith("172.")
        ):
            return None
        return resolved

    og_url = soup.find("meta", property="og:url")
    if og_url and og_url.get("content"):
        resolved = absolute_url(base_url, og_url["content"])
        parsed = urlparse(resolved)
        if parsed.hostname in INVALID_CANONICAL_HOSTS:
            return None
        return resolved

    return None