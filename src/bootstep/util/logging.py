from logging import StreamHandler, LogRecord
from typing import TYPE_CHECKING, TextIO

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
