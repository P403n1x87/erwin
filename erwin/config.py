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

from appdirs import user_config_dir
import os
import os.path
import signal
import yaml

from erwin import APP_NAME
from erwin.fs import FSNotReady, State
from erwin.logging import LOGGER


CONFIG_DIR = user_config_dir(APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yml")

STATES_DIR = os.path.join(CONFIG_DIR, "states")
TOKENS_DIR = os.path.join(CONFIG_DIR, "tokens")


class ErwinConfiguration:
    SIGNALS = [signal.SIGINT, signal.SIGTERM]

    def __init__(self):
        self._orig_sig_handlers = None
        self._master_state = None
        self._slave_state = None
        self._master_state_file = None
        self._slave_state_file = None

    def __enter__(self):
        try:
            with open(CONFIG_FILE, "r") as cf:
                self._config = yaml.safe_load(cf)
        except FileNotFoundError:
            self.do_initial_config()

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._orig_sig_handlers:
            LOGGER.debug("Restoring signal handlers")
            for h, s in zip(self._orig_sig_handlers, self.SIGNALS):
                signal.signal(s, h)

        if exc_value and exc_type not in (FSNotReady,):
            LOGGER.critical(
                f"Emergency shutdown. Current FS states persisted. Cause: {exc_value}"
            )
            raise exc_value

    def do_initial_config(self):
        for folder in [CONFIG_DIR, STATES_DIR, TOKENS_DIR]:
            os.makedirs(folder, exist_ok=True)

        print(
            "Hello. I'm Erwin. It appears this is the first time you invoked\n"
            "me :). Let me guide you through the configuration process.\n"
            "\n"
            "First, I need an alias for your account configuration"
        )

        alias = input("> ")

        print(
            "\nGreat! Now tell me where the root of the local copy of your\n"
            "Google Drive folder should be"
        )

        root = input("> ")
        os.makedirs(os.path.expanduser(root), exist_ok=True)
        # TODO: Validate!

        print(
            "\nExcellent! That's all! I will now start synchronising your\n"
            "Google Drive files for you!"
        )

        self._config = {
            alias: {
                "slave_fs": {"params": {"root": root}},
                "master_fs": {
                    "params": {"token": os.path.join(TOKENS_DIR, f"{alias}.pickle")}
                },
            }
        }

        with open(CONFIG_FILE, "w") as cf:
            yaml.safe_dump(self._config, cf)

    def _save_states(self, signum=None, frame=None):
        if signum:
            print("")
            LOGGER.warn(f"Received termination signal ({signum}). Shutting down...")

        if self._master_state:
            self._master_state.save(self._master_state_file)
            LOGGER.info("Master FS state saved")

            self._slave_state.save(self._slave_state_file)
            LOGGER.info("Slave FS state saved")

        if signum:
            exit(signum)

    def load_fs_states(self, alias=None):
        if not alias:
            alias, = self._config.keys()

        self._master_state_file = os.path.join(STATES_DIR, f"{alias}_master.pickle")
        master_state = State.load(self._master_state_file)
        LOGGER.debug(f"Previous state of Master FS loaded")

        self._slave_state_file = os.path.join(STATES_DIR, f"{alias}_slave.pickle")
        slave_state = State.load(self._slave_state_file)
        LOGGER.debug("Previous state of Slave FS loaded")

        return master_state, slave_state

    def register_state_handler(self, master_state, slave_state):
        self._master_state = master_state
        self._slave_state = slave_state
        self._orig_sig_handlers = [
            signal.signal(s, self._save_states) for s in self.SIGNALS
        ]

    def _get_fs_params(self, alias, fs):
        if not alias:
            alias, = self._config.keys()

        return self._config[alias][f"{fs}_fs"]["params"]

    def get_master_fs_params(self, alias=None):
        return self._get_fs_params(alias, "master")

    def get_slave_fs_params(self, alias=None):
        return self._get_fs_params(alias, "slave")
