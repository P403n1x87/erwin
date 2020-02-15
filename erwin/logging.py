import logging
import os


logging.basicConfig(
    level=getattr(logging, os.environ.get("ERWIN_DEBUG_LEVEL", "DEBUG").upper()),
    format="{asctime}.{msecs:03.0f} [{name}] {levelname:8} {message} "
    "({filename}@{lineno}, in {funcName})",
    style="{",
    datefmt="%H:%M:%S",
)


LOGGER = logging.getLogger("erwin")

logging.getLogger("watchdog").setLevel(logging.WARNING)
