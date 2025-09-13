import logging
import sys


class ContextDefaultsFilter(logging.Filter):
    """Ensure contextual fields exist to avoid KeyError in formatters."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        for field, default in (
            ("channel_id", "-"),
            ("user_id", "-"),
            ("operation", "-"),
        ):
            if not hasattr(record, field):
                setattr(record, field, default)
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger for the application with contextual fields."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.addFilter(ContextDefaultsFilter())
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | op=%(operation)s | ch=%(channel_id)s | user=%(user_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
