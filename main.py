import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import ProcessPoolExecutor
import os
import shutil
from pathlib import Path
import time


from data.logs import *
from etc import *
from data.transform import *
from utils import *
import yaml


filename = "./data/logos.snappy.parquet"
df = pq.read_table(filename).to_pandas()

def extractData():

    shutil.rmtree(config['extract_folder'])
    os.makedirs(config['extract_folder'], exist_ok=True)
    ####

    domains = df["domain"].dropna().head(20).tolist()
    results = []
    ###
    setup_logging(config['scrapping_path'])
    with ThreadPoolExecutor(max_workers=config['MAX_Threads']) as executor:
        futures = {executor.submit(process_domain, domain): domain for domain in domains}

        for future in as_completed(futures):
            domain, logo_url, error = future.result()
            if error:
                logging.error(f"{domain}: {error}")
            elif logo_url:
                logging.info(f"OK: {domain}: {error}")
            else:
                logging.warning(f"No logo found: {domain}: {error}!")
            results.append({"domain": domain, "logo_url": logo_url, "error": error})

    ### Save results summary
    logging.info(f"\nDone. {sum(1 for r in results if r['logo_url'])} logos found out of {len(results)}")


def proccesData(folder: Path, output_folder: Path):

    # --- 1. Process & cache all logos ---
    MAX_CPUS = config['MAX_CPUS']
    processed = {}
    valid_ext = {".png", ".jpg", ".jpeg", ".svg"}
    ###
    files = [p for p in folder.iterdir() if p.suffix.lower() in valid_ext]
    with ProcessPoolExecutor(max_workers=MAX_CPUS) as executor:
        futures = {executor.submit(processLogos, p): p for p in files}

        for future in as_completed(futures):
            stem, result, err = future.result()

            if err:
                logging.error(f"SKIPPED: {stem} — {err}")
                continue

            processed[stem] = result

    save_debug_masks(processed, output_folder, n=len(processed))

    # --- 2. Compare all pairs ---
    with ProcessPoolExecutor(max_workers=MAX_CPUS) as executor:
        future = executor.submit(comparePairs, processed)
        results, stems = future.result() 

    logging.info(f"\nDone. Found {len(results)} similar pairs out of {len(stems)*(len(stems)-1)//2} total.")

    
if __name__ == "__main__":

    file = open('./etc/config.yaml', 'r')
    config = yaml.safe_load(file)

    ####
    start = time.perf_counter()
    extractData()
    timeToScrape = time.perf_counter()

    ####    
    setup_logging(config['proccesing_path'])

    shutil.rmtree(config['transform_folder'])
    os.makedirs(config['transform_folder'], exist_ok=True)

    proccesData(folder=Path(config['extract_folder']), output_folder=Path(config['transform_folder']))

    timeToProcess = time.perf_counter()

    print(f"Time scrapping: {timeToScrape - start:.3f} seconds")
    print(f"Total time: {timeToProcess - timeToScrape:.3f} seconds")