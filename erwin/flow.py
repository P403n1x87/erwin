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

from threading import RLock
from time import sleep

from erwin.fs import FSNotReady
from erwin.logging import LOGGER


GLOBAL_LOCK = RLock()


def atomic(lock=GLOBAL_LOCK):
    def atomic_wrapper(f):
        def func_wrapper(*args, **kwargs):
            with lock:
                return f(*args, **kwargs)

        return func_wrapper

    return atomic_wrapper


def backoff(delay=5, ratio=1.618, cap=60):
    def wrapper(f):
        def func_wrapper(*args, **kwargs):
            backoff = delay
            while True:
                try:
                    error = False
                    return f(*args, **kwargs)
                except FSNotReady as e:
                    LOGGER.error(f"A file system is not ready yet: {e}")
                    LOGGER.info(
                        f"A new start attempt will be made in {int(backoff)} seconds"
                    )
                    sleep(backoff)
                    backoff = min(cap, backoff * ratio)
                    error = True
                finally:
                    if not error:
                        backoff = delay

        return func_wrapper

    return wrapper
