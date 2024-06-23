import logging
import logging.config
from pathlib import Path

import yaml

from config import AIXCC_CRS_SCRATCH_SPACE


def filter_maker(level):
    level = getattr(logging, level)

    def filter(record):
        return record.levelno <= level

    return filter


def make_logger():
    log_conf = yaml.safe_load(
        Path(Path.cwd() / "py" / 'logging.yaml').read_text()
    )
    log_conf["handlers"]["file"]["filename"] = (AIXCC_CRS_SCRATCH_SPACE / "crs.log").resolve()

    logging.config.dictConfig(
        log_conf
    )
    return logging.getLogger('CRS')


logger = make_logger()
