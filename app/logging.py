import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(stream=sys.stdout),
        ],
    )
