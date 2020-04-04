from ansimarkup import parse
import logging
import os


class ColorFormatter(logging.Formatter):
    ANSI_PALETTE = {
        "TRACE": "<white>{}</white>",
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

# Add TRACE level
TRACE_LEVEL = logging.NOTSET + 1

logging.addLevelName(TRACE_LEVEL, "TRACE")
logging.TRACE = TRACE_LEVEL


def _trace(self, message, *args, **kwargs):
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)


type(LOGGER).trace = _trace


# Configure formatter and handler
_handler = logging.StreamHandler()
_handler.setFormatter(
    ColorFormatter(
        "{asctime}.{msecs:03.0f} [{name}] <b>{levelname:18}</b> <yellow>{threadName:12}</yellow> {message} "
        "<fg 128,128,128>({filename}@{lineno}, in <b>{funcName}</b>)</fg 128,128,128>",
        style="{",
        datefmt="%H:%M:%S",
    )
)
LOGGER.addHandler(_handler)


# Set logger level
LOGGER.setLevel(getattr(logging, os.environ.get("ERWIN_DEBUG_LEVEL", "INFO").upper()))


# Suppress third-party libraries logging messages from INFO downwards
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)
