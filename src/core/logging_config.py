import logging
import re
from core.config import settings


class PIIFilter(logging.Filter):
    """Redacts email addresses from log messages before they are written."""
    _EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._EMAIL_PATTERN.sub("[EMAIL REDACTED]", str(record.msg))
        if record.args:
            record.args = tuple(
                self._EMAIL_PATTERN.sub("[EMAIL REDACTED]", str(a))
                if isinstance(a, str) else a
                for a in (record.args if isinstance(record.args, tuple) else (record.args,))
            )
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(PIIFilter())
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        handlers=[handler],
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )
