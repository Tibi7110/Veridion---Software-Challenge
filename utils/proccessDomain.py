from etc import *

def process_domain(domain: str) -> tuple[str, str | None, str | None]:
    """Returns (domain, logo_url, error)"""
    website = f"https://{domain}"
    try:
        website = resolve_final_url(website)
        logo_url = extract_logo(website)
        if logo_url:
            filename = f"logos/{domain.replace('.', '_')}.png"
            download_logo(logo_url, filename)
            return domain, logo_url, None
        else:
            return domain, None, None
    except Exception as e:
        return domain, None, str(e)
