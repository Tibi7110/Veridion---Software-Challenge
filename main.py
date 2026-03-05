import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import shutil

from utils.logs import *
from etc import *
import yaml


filename = "./data/logos.snappy.parquet"
df = pq.read_table(filename).to_pandas()

'''
// Logging 

logging.info("Everything is info")
logging.debug("Everything is debug")
logging.warning("Everything is warning")
logging.error("Everything is error")
logging.critical("Everything is critical")

file = open('./utils/config.yaml', 'r')
config = yaml.safe_load(file)

name = config['name']
'''

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
    
if __name__ == "__main__":
    
    shutil.rmtree("logos")
    os.makedirs("logos", exist_ok=True)
    domains = df["domain"].dropna().head(10).tolist()

    MAX_WORKERS = 8  # keep low — Playwright is memory-heavy (~150MB per browser)

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_domain, domain): domain for domain in domains}

        for future in as_completed(futures):
            domain, logo_url, error = future.result()
            if error:
                print(f"❌ {domain}: {error}")
            elif logo_url:
                print(f"✅ {domain}: {logo_url}")
            else:
                print(f"⚠️  {domain}: No logo found")
            results.append({"domain": domain, "logo_url": logo_url, "error": error})

    # Save results summary
    results_df = pd.DataFrame(results)
    results_df.to_csv("logo_results.csv", index=False)
    print(f"\nDone. {sum(1 for r in results if r['logo_url'])} logos found out of {len(results)}")
