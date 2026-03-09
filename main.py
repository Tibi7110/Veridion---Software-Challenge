import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import ProcessPoolExecutor
import os
import shutil
from pathlib import Path
import time


from utils.logs import *
from etc import *
from data.transform import *
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
    
def process_data(p):
    print(f"Processing {p.name}...")
    try:
        result = process_logo(str(p))
        return (p.stem, result, None)
    except Exception as e:
        return (p.stem, None, e)

    
if __name__ == "__main__":

    MAX_Threads = 50  # keep low — Playwright is memory-heavy (~150MB per browser)

    shutil.rmtree("logos")
    os.makedirs("logos", exist_ok=True)
    domains = df["domain"].dropna().head(125).tolist()

    results = []
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=MAX_Threads) as executor:
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

    end = time.perf_counter()
    print(f"Total time: {end - start:.3f} seconds")
    # Save results summary
    print(f"\nDone. {sum(1 for r in results if r['logo_url'])} logos found out of {len(results)}")
    

    shutil.rmtree("logos2", ignore_errors=True)
    os.makedirs("logos2", exist_ok=True)

    shutil.rmtree("/home/tibi/Proiecte/Veridion/logos2")
    os.makedirs("logos2", exist_ok=True)
    folder = Path("/home/tibi/Proiecte/Veridion/logos")
    output_folder = Path("/home/tibi/Proiecte/Veridion/logos2")
    valid_ext = {".png", ".jpg", ".jpeg", ".svg"}

    # --- 1. Process & cache all logos ---
    processed = {}
    MAX_CPUS = 8
    files = [p for p in folder.iterdir() if p.suffix.lower() in valid_ext]
    with ProcessPoolExecutor(max_workers=MAX_CPUS) as executor:
        futures = {executor.submit(process_data, p): p for p in files}

        for future in as_completed(futures):
            stem, result, err = future.result()

            if err:
                print(f"SKIPPED: {stem} — {err}")
                continue

            processed[stem] = result

    save_debug_masks(processed, output_folder, n=len(processed))

    # --- 2. Compare all pairs ---
    stems = list(processed.keys())
    results = []

    print("\n--- ALL PAIRS DEBUG ---")
    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            name1, name2 = stems[i], stems[j]
            p1, p2 = processed[name1], processed[name2]
            bw1 = resize_bw(p1["bw"])
            bw2 = resize_bw(p2["bw"])
            mse     = compute_normalized_mse(bw1, bw2)
            hamming = hamming_distance(p1["phash"], p2["phash"])
            similar  = hamming < 10 and mse < 0.2
            if similar:
                results.append((name1, name2, hamming, mse))
                print(f"  SIMILAR: {name1} <-> {name2} | hamming={hamming} | mse={mse:.2f}")

    print(f"\nDone. Found {len(results)} similar pairs out of {len(stems)*(len(stems)-1)//2} total.")

