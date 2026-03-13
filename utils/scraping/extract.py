import base64
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
import requests

from .url import is_url_accessible, absolute_url, HEADERS

def extract_css_logo(soup: BeautifulSoup, base_url: str) -> str | None:
    """Extract logo from CSS background-image properties."""
    bg_url_pattern = re.compile(r'url\(["\']?([^)"\']+)["\']?\)')

    def scan_css_text(css_text: str) -> str | None:
        """Find a background-image URL containing 'logo' in a block of CSS."""
        if "logo" not in css_text.lower():
            return None
        # Find all url(...) occurrences near the word "logo"
        for match in bg_url_pattern.finditer(css_text):
            path = match.group(1).strip()
            if not path or path.startswith("data:"):
                continue
            # Check surrounding context (~200 chars) for "logo"
            start = max(0, match.start() - 200)
            end = min(len(css_text), match.end() + 200)
            context = css_text[start:end].lower()
            if "logo" in context:
                return path
        return None

    # 1. Inline <style> blocks
    for style_tag in soup.find_all("style"):
        result = scan_css_text(style_tag.get_text())
        if result:
            return absolute_url(base_url, result)

    # 2. Inline style= attributes on logo-related elements
    for tag in soup.find_all(style=True):
        attrs = " ".join([
            " ".join(str(c) for c in (tag.get("class") or [])),
            str(tag.get("id", ""))
        ]).lower()
        if "logo" not in attrs:
            continue
        result = scan_css_text(tag["style"])
        if result:
            return absolute_url(base_url, result)

    # 3. External stylesheets via <link rel="stylesheet">
    for link in soup.find_all("link", rel=lambda r: bool(r and "stylesheet" in r)):
        href = link.get("href")
        if not href:
            continue
        css_url = absolute_url(base_url, href)
        try:
            resp = requests.get(css_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            result = scan_css_text(resp.text)
            if result:
                # CSS url() paths are relative to the CSS file's location, not the page
                candidate = absolute_url(css_url, result)
                if candidate and is_url_accessible(candidate, referer=base_url):
                    return candidate
        except Exception:
            continue

    return None 

def extract_inline_svg(soup: BeautifulSoup, url: str) -> str | None:
    """Find inline SVG logos and convert to a data URI or save as file."""
    
    # Look for <svg> inside logo-related parent elements
    for tag in soup.find_all(class_=re.compile(r'logo', re.I)):
        svg = tag.find("svg")
        if svg:
            return "data:image/svg+xml;base64," + base64.b64encode(str(svg).encode()).decode()
    
    for tag in soup.find_all(id=re.compile(r'logo', re.I)):
        svg = tag.find("svg")
        if svg:
            return "data:image/svg+xml;base64," + base64.b64encode(str(svg).encode()).decode()

    # Also check <svg> directly with logo-related attributes
    for svg in soup.find_all("svg"):
        attrs = " ".join([
            str(svg.get("id", "")),
            " ".join(str(c) for c in (svg.get("class") or [])),
            str(svg.get("aria-label", "")),
            str(svg.get("title", ""))
        ]).lower()
        if "logo" in attrs:
            return "data:image/svg+xml;base64," + base64.b64encode(str(svg).encode()).decode()

    return None



def extract_favicon(soup: BeautifulSoup, url: str) -> str | None:
    # Prefer high-res touch icons over tiny favicons
    selectors = [
        {"rel": "apple-touch-icon"},
        {"rel": "apple-touch-icon-precomposed"},
        {"rel": lambda r: r and "icon" in " ".join(r).lower() and "mask" not in " ".join(r).lower()},
    ]
    best = (0, None)
    for attrs in selectors:
        for link in soup.find_all("link", **attrs):
            href = link.get("href")
            if not href:
                continue
            sizes = link.get("sizes", "0x0")
            try:
                size = int(sizes.split("x")[0]) if sizes != "any" else 999
            except (ValueError, IndexError):
                size = 1
            if size > best[0]:
                best = (size, absolute_url(url, href))
    
    if best[1]:
        return best[1]

    # Last resort: try /favicon.ico
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"


def extract_img_logo(soup: BeautifulSoup, url: str) -> str | None:
    logo_candidates = []
    for img in soup.find_all("img"):
        score = 0
        src = None
        attrs = " ".join([
            str(img.get("alt", "")),
            " ".join(str(c) for c in (img.get("class") or [])),
            str(img.get("id", ""))
        ]).lower()
        if "logo" in attrs:
            score += 50
        if img.get("src"):
            src = str(img["src"])
            if "logo" in src.lower():
                score += 30
        if score > 0:
            logo_candidates.append((score, src))

    for score, src in sorted(logo_candidates, key=lambda x: x[0], reverse=True):
        candidate = absolute_url(url, src)
        if candidate and is_url_accessible(candidate, referer=url):
            return candidate

    header = soup.find("header")
    if header:
        img = header.find("img")
        if img and img.get("src"):
            src = img["src"]
            if isinstance(src, list):
                src = src[0]
            candidate = absolute_url(url, src)
            if candidate and is_url_accessible(candidate, referer=url):
                return candidate

    return None


def extract_og_logo(soup: BeautifulSoup, url: str) -> str | None:
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        content = og["content"]
        if isinstance(content, list):
            content = content[0]
        candidate = absolute_url(url, content)
        if candidate and is_url_accessible(candidate, referer=url):
            return candidate

    return None
