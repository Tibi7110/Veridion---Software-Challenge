import logging
from pathlib import Path

LOG_FORMAT = (
    "%(asctime)s | In file: %(filename)s, Function: %(funcName)s, Line: %(lineno)s "
    "| %(levelname)s | %(message)s"
)


def setup_logging(filename: str = "scrapping.log", filemode: str = "w") -> None:
    "Function to edit logs filepath"

    log_path = Path(filename)

    logging.getLogger().handlers.clear()

    logging.basicConfig(
        filename=str(log_path),
        filemode=filemode,
        level=logging.INFO,
        format=LOG_FORMAT,
    )
