import logging

logging.basicConfig(
    filename='websites.log',
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s | In file: %(filename)s, Function: %(funcName)s, Line: %(lineno)s  | %(levelname)s | %(message)s',
)