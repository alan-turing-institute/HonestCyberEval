import logging
import logging.config
from pathlib import Path

import yaml


class MultiLineFormatter(logging.Formatter):
    """Multi-line formatter.
    https://stackoverflow.com/a/66855071
    """

    def get_header_length(self, record):
        """Get the header length of a given record."""
        return len(
            super().format(
                logging.LogRecord(
                    name=record.name,
                    level=record.levelno,
                    pathname=record.pathname,
                    lineno=record.lineno,
                    msg="",
                    args=(),
                    exc_info=None,
                )
            )
        )

    def format(self, record):
        """Format a record with added indentation."""
        indent = " " * self.get_header_length(record)
        head, *trailing = super().format(record).splitlines(True)
        return head + "".join(indent + line for line in trailing)


def filter_maker(level):
    level = getattr(logging, level)

    def filter(record):
        return record.levelno <= level

    return filter


def make_logger():
    log_conf = yaml.safe_load((Path(__file__).parent / "logging.yaml").read_text())
    logging.config.dictConfig(log_conf)
    return logging.getLogger("CRS")


logger = make_logger()
