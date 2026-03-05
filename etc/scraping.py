import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
import json
import re
import base64
import cairosvg


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

def resolve_final_url(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        final = resp.url
        parsed = urlparse(final)
        if (parsed.scheme == "https" and parsed.port == 443) or \
           (parsed.scheme == "http" and parsed.port == 80):
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

TRUSTED_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}

def is_url_accessible(url: str, referer: str = None) -> bool:
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

def absolute_url(base_url, path):

    if not path or not isinstance(path, str):
        return None
    return urljoin(base_url, path)


def fetch_html(url: str):
    if url.startswith("http://"):
        url = url.replace("http://", "https://")

    resolved = resolve_final_url(url)
    if resolved != url:
        print(f"  Pre-resolved redirect: {url} -> {resolved}")
        url = resolved

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)
        try:
            html = _try_fetch(browser, url)

        except PlaywrightError as e:
            error_str = str(e)
            parsed = urlparse(url)
            if any(err in error_str for err in (
                "ERR_CONNECTION_CLOSED",
                "ERR_CONNECTION_REFUSED",
                "ERR_CONNECTION_TIMED_OUT",
                "ERR_ADDRESS_UNREACHABLE",
                "ERR_SSL_VERSION_OR_CIPHER_MISMATCH",
                "ERR_NAME_NOT_RESOLVED"
            )) and not parsed.netloc.startswith("www."):
                www_url = f"{parsed.scheme}://www.{parsed.netloc}{parsed.path}"
                print(f"  Retrying with www: {www_url}")
                try:
                    html = _try_fetch(browser, www_url)
                except PlaywrightError as e2:
                    raise ValueError(f"Failed to load page (www fallback also failed): {e2}")
            elif "ERR_NAME_NOT_RESOLVED" in error_str and not parsed.netloc.startswith("www."):
                www_url = f"{parsed.scheme}://www.{parsed.netloc}{parsed.path}"
                print(f"  Retrying with www: {www_url}")
                try:
                    html = _try_fetch(browser, www_url)
                except PlaywrightError as e2:
                    raise ValueError(f"Domain does not resolve: {url}")
            else:
                raise ValueError(f"Failed to load page: {e}")
            
        finally:
            browser.close()

    return BeautifulSoup(html, "html.parser")


def _try_fetch(browser, url: str) -> str:
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
        # Spoof a real browser fingerprint
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36",
        extra_http_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
    )
    page = context.new_page()

    # Remove webdriver flag that Cloudflare detects
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)

    try:
        try:
            page.goto(url, timeout=40000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            print(f"  networkidle timeout, falling back to domcontentloaded for {url}")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except PlaywrightTimeoutError:
                pass

            # Dismiss cookie consent walls
            consent_selectors = [
                "button[id*='accept' i]", "button[class*='accept' i]",
                "button[id*='cookie' i]", "button[class*='cookie' i]",
                "button[id*='consent' i]", "button[class*='consent' i]",
                "button[title*='accept' i]", "button[aria-label*='accept' i]",
                "#onetrust-accept-btn-handler", ".cookie-accept",
                "[data-testid*='accept' i]",
            ]
            for selector in consent_selectors:
                try:
                    btn = page.wait_for_selector(selector, timeout=1000)
                    if btn:
                        btn.click()
                        print(f"  Dismissed consent wall via: {selector}")
                        page.wait_for_timeout(1500)
                        break
                except PlaywrightTimeoutError:
                    continue

            try:
                page.wait_for_selector(
                    "img[alt*='logo' i], img[src*='logo' i], "
                    "[class*='logo' i] img, [class*='logo' i] svg, "
                    "header img, header svg",
                    timeout=8000
                )
            except PlaywrightTimeoutError:
                page.wait_for_timeout(2000)

        return page.content()
    finally:
        page.close()
        context.close()


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


def extract_logo(url: str) -> str | None:
    resolved = resolve_final_url(url)
    if resolved != url:
        print(f"  Using resolved URL for scraping: {resolved}")
        url = resolved

    soup = fetch_html(url)

    canonical = extract_canonical_url(soup, url)
    if canonical:
        canonical_netloc = urlparse(canonical).netloc
        current_netloc = urlparse(url).netloc
        # Only re-fetch if canonical is on a genuinely different domain AND not already visited
        if canonical_netloc != current_netloc and canonical != url:
            print(f"  Canonical URL points elsewhere: {canonical}, re-fetching...")
            url = canonical
            soup = fetch_html(url)
        # If same domain but different path, just update base url for absolute_url resolution
        elif canonical_netloc == current_netloc and canonical != url:
            url = canonical  # update base URL but don't re-fetch


    # 1. og:image meta tag
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        content = og["content"]
        if isinstance(content, list):
            content = content[0]
        candidate = absolute_url(url, content)
        if candidate and is_url_accessible(candidate, referer=url):
            return candidate
        print(f"  og:image not accessible ({candidate}), trying next strategy...")

    # 2. <img> tags scored by logo-related attributes
    logo_candidates = []
    for img in soup.find_all("img"):
        score = 0
        attrs = " ".join([
            str(img.get("alt", "")),
            " ".join(str(c) for c in (img.get("class") or [])),
            str(img.get("id", ""))
        ]).lower()
        if "logo" in attrs:
            score += 50
        if img.get("src"):
            src = img["src"]
            if isinstance(src, list):
                src = src[0]
            if "logo" in src.lower():
                score += 30
        if score > 0:
            logo_candidates.append((score, src))

    # Try candidates in order of score, skip inaccessible ones
    for score, src in sorted(logo_candidates, key=lambda x: x[0], reverse=True):
        candidate = absolute_url(url, src)
        if candidate and is_url_accessible(candidate, referer=url):
            return candidate
        print(f"  img candidate not accessible ({candidate}), skipping...")

    # 3. CSS background-image containing "logo"
    css_logo = extract_logo_from_css(soup, url)
    if css_logo and is_url_accessible(css_logo, referer=url):
        return css_logo
    elif css_logo:
        print(f"  CSS logo not accessible ({css_logo}), trying next strategy...")

    # 4. Inline SVG logo
    svg_logo = extract_inline_svg(soup, url)
    if svg_logo:
        return svg_logo

    # 5. First <img> inside <header>
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

    # 6. Favicon as last resort (better than nothing for brand identification)
    favicon = extract_favicon(soup, url)
    if favicon and is_url_accessible(favicon, referer=url):
        print(f"  Using favicon as fallback: {favicon}")
        return favicon

    return None


def extract_logo_from_css(soup: BeautifulSoup, base_url: str) -> str | None:
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
                return absolute_url(css_url, result)
        except Exception:
            continue

    return None

def fix_malformed_redirect(url: str, original_url: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc

    # Detect if the netloc has a known TLD fused with a path segment
    # e.g. "www.astrazeneca.uaetc" -> host is "www.astrazeneca.ua", leaked path is "etc"
    # Strategy: find the real host by matching known TLD boundary
    tld_pattern = re.compile(
        r'^((?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,6})([a-zA-Z0-9].*)$'
    )

    # Check if netloc ends with a valid TLD or has garbage fused on
    # We'll try to split at the TLD boundary using the original host as a hint
    original_parsed = urlparse(original_url)
    original_host = original_parsed.hostname  # e.g. "astrazeneca.ua"

    if original_host:
        # Extract the TLD from original host (last two parts: "astrazeneca.ua" -> tld = "ua")
        parts = original_host.split(".")
        tld = parts[-1]  # e.g. "ua"

        # Check if netloc contains ".{tld}" followed by extra chars
        tld_marker = f".{tld}"
        tld_index = netloc.find(tld_marker)
        if tld_index != -1:
            tld_end = tld_index + len(tld_marker)
            if tld_end < len(netloc):
                # There's garbage after the TLD
                real_host = netloc[:tld_end]          # "www.astrazeneca.ua"
                leaked_path = "/" + netloc[tld_end:]  # "/etc"
                fixed_path = leaked_path + parsed.path  # "/etc/designs/az/img/..."
                fixed_url = parsed._replace(netloc=real_host, path=fixed_path).geturl()
                print(f"  Fixed malformed redirect: {url!r} -> {fixed_url!r}")
                return fixed_url

    return url


def download_logo(logo_url: str, filename: str, referer: str = None):
    if logo_url.startswith("data:image/svg+xml;base64,"):
        svg_data = base64.b64decode(logo_url.split(",", 1)[1])
        svg_filename = filename.rsplit(".", 1)[0] + ".svg"
        with open(svg_filename, "wb") as f:
            f.write(svg_data)
        return

    # Harvest cookies from the referer page so requests.Session is fully authenticated
    harvested_cookies = {}
    if referer:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=HEADERS["User-Agent"])
                page = context.new_page()
                try:
                    page.goto(referer, timeout=20000)
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                # ✅ Extract all cookies from the browser context
                for cookie in context.cookies():
                    harvested_cookies[cookie["name"]] = cookie["value"]
                page.close()
                context.close()
                browser.close()
        except Exception as e:
            print(f"  Cookie harvest failed ({e}), continuing without cookies...")

    # Try requests.Session with harvested cookies + referer header
    headers = {**HEADERS}
    if referer:
        headers["Referer"] = referer
    try:
        session = requests.Session()
        # ✅ Inject harvested browser cookies into the requests session
        for name, value in harvested_cookies.items():
            session.cookies.set(name, value)
        response = session.get(logo_url, headers=headers, timeout=15, stream=True, allow_redirects=True)
        if response.status_code == 200:
            with open(filename, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return
        print(f"  requests download failed ({response.status_code}), trying Playwright...")
    except Exception as e:
        print(f"  requests download failed ({e}), trying Playwright...")

    # Fallback: Playwright context.request (CORS-free, shares browser cookies)
    # Fallback: intercept the image by navigating to it within a real page context
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            extra_http_headers={
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            }
        )
        try:
            # Visit referer first to establish cookies/session
            if referer:
                page = context.new_page()
                try:
                    page.goto(referer, timeout=20000)
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                finally:
                    page.close()

            # ✅ Intercept the image response via routing — fires as a real browser sub-request
            image_bytes = None

            def handle_route(route, request):
                response = route.fetch()  # fetched with full browser TLS fingerprint + cookies
                nonlocal image_bytes
                image_bytes = response.body()
                route.fulfill(response=response)

                page = context.new_page()
                page.route(logo_url, handle_route)
                try:
                    # Navigate directly to the image URL — triggers the route handler
                    page.goto(logo_url, timeout=20000)
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                finally:
                    page.close()
        
                if not image_bytes:
                    raise ValueError("No image bytes captured via route intercept")
        
                ext = "." + logo_url.rsplit(".", 1)[-1].split("?")[0].lower()
                actual_filename = filename.rsplit(".", 1)[0] + ext
                with open(actual_filename, "wb") as f:
                    f.write(image_bytes)
        
        finally:
            context.close()
            browser.close()