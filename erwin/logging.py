from ansimarkup import parse
import logging
import os


class ColorFormatter(logging.Formatter):
    ANSI_PALETTE = {
        "DEBUG": "<cyan>{}</cyan>",
        "INFO": "<green>{}</green>",
        "WARNING": "<yellow>{}</yellow>",
        "ERROR": "<red>{}</red>",
        "CRITICAL": "<red>{}</red>",
    }

    def format(self, record):
        record.levelname = parse(
            ColorFormatter.ANSI_PALETTE[record.levelname].format(record.levelname)
        )
        return parse(super().format(record))


LOGGER = logging.getLogger("erwin")
_handler = logging.StreamHandler()
_handler.setFormatter(
    ColorFormatter(
        "{asctime}.{msecs:03.0f} [{name}] <b>{levelname:18}</b> {message} "
        "<fg 128,128,128>({filename}@{lineno}, in <b>{funcName}</b>)</fg 128,128,128>",
        style="{",
        datefmt="%H:%M:%S",
    )
)
LOGGER.addHandler(_handler)
LOGGER.setLevel(getattr(logging, os.environ.get("ERWIN_DEBUG_LEVEL", "INFO").upper()))

logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)
