from logging import StreamHandler, LogRecord
import logging.config
import os.path
from typing import TYPE_CHECKING, TextIO

from ..util.filesys import make_dir, user_data_dir

if TYPE_CHECKING:
    BaseStreamHandler = StreamHandler[TextIO]
else:
    BaseStreamHandler = StreamHandler


# hat tip to Martijn Pieters https://stackoverflow.com/a/54605728/268977


class NoTracebackStreamHandler(BaseStreamHandler):
    def handle(self, record: LogRecord) -> bool:
        info, cache = record.exc_info, record.exc_text
        record.exc_info, record.exc_text = None, None
        try:
            return super().handle(record)
        finally:
            record.exc_info, record.exc_text = info, cache


config_logging = logging.config.dictConfig


def user_log_file(name: str, make: bool = False) -> str:
    dir = os.path.join(user_data_dir(), name)
    if make:
        make_dir(dir, deep=True, exist_ok=True)
    return os.path.join(dir, f"{name}.log")
