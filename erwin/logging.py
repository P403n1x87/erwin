# This file is part of "erwin" which is released under GPL.
#
# See file LICENCE or go to http://www.gnu.org/licenses/ for full license
# details.
#
# Erwin is a cloud storage synchronisation service.
#
# Copyright (c) 2020 Gabriele N. Tornetta <phoenix1987@gmail.com>.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from appdirs import user_log_dir
from ansimarkup import parse
import logging
from logging.handlers import RotatingFileHandler
import os
import os.path

from erwin import APP_NAME, AUTHOR

LOG_FOLDER = user_log_dir(APP_NAME, AUTHOR)
os.makedirs(LOG_FOLDER, exist_ok=True)


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

_rfile_handler = RotatingFileHandler(
    os.path.join(LOG_FOLDER, APP_NAME + ".log"), maxBytes=4096, backupCount=1
)
_rfile_handler.setFormatter(
    logging.Formatter(
        "{asctime}.{msecs:03.0f} [{name}] {levelname:18} {threadName:12} {message} "
        "({filename}@{lineno}, in {funcName})",
        style="{",
        datefmt="%H:%M:%S",
    )
)
LOGGER.addHandler(_rfile_handler)


# Set logger level
LOGGER.setLevel(getattr(logging, os.environ.get("ERWIN_DEBUG_LEVEL", "INFO").upper()))


# Suppress third-party libraries logging messages from INFO downwards
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.WARNING)
