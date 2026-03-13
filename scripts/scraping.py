import base64
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
import requests

from utils.scraping import *

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
            page.goto(url, timeout=30000)
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
        # If same domain but different path, just update base url for absolute_url resolution
        elif canonical_netloc == current_netloc and canonical != url:
            url = canonical  # update base URL but don't re-fetch

    for strategy in (
        extract_img_logo,
        extract_og_logo,
        extract_css_logo,
        extract_inline_svg,
    ):
        result = strategy(soup, url)
        if result:
            return result

    favicon = extract_favicon(soup, url)
    if favicon and is_url_accessible(favicon, referer=url):
        print(f"  Using favicon as fallback: {favicon}")
        return favicon

    return None

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
                    page.goto(referer, timeout=10000)
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                # Extract all cookies from the browser context
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
        # Inject harvested browser cookies into the requests session
        for name, value in harvested_cookies.items():
            session.cookies.set(name, value)
        response = session.get(logo_url, headers=headers, timeout=10, stream=True, allow_redirects=True)
        if response.status_code == 200:
            # Derive extension from URL, fall back to Content-Type
            url_ext = "." + logo_url.rsplit(".", 1)[-1].split("?")[0].lower() if "." in logo_url else ""
            content_type = response.headers.get("Content-Type", "")
            ct_map = {
                "image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg",
                "image/webp": ".webp", "image/gif": ".gif",
                "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico",
            }
            ct_ext = next((v for k, v in ct_map.items() if k in content_type), "")
            trusted = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}
            ext = url_ext if url_ext in trusted else ct_ext or url_ext
            actual_filename = filename.rsplit(".", 1)[0] + ext if ext else filename
            with open(actual_filename, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return

        print(f"  requests download failed ({response.status_code}), trying Playwright...")
    except Exception as e:
        print(f"  requests download failed ({e}), trying Playwright...")

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

            # Intercept the image response via routing — fires as a real browser sub-request
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