import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from utils.logs import *
import yaml 

filename = "./data/logos.snappy.parquet"
df = pq.read_table(filename).to_pandas()

logging.info("Everything is info")
logging.debug("Everything is debug")
logging.warning("Everything is warning")
logging.error("Everything is error")
logging.critical("Everything is critical")

file = open('./utils/config.yaml', 'r')
config = yaml.safe_load(file)

name = config['name']

print(name)
