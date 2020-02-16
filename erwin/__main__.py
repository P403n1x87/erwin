from appdirs import user_config_dir

from enum import Enum, auto
import os.path
import signal
from shutil import copyfile
import threading
from time import sleep
import yaml

from erwin.fs import FileSystem
from erwin.fs.drive import GoogleDriveFS, GoogleDriveFSState
from erwin.fs.local import LocalFS, LocalFSState
from erwin.logging import LOGGER


APP_NAME = "erwin"
CONFIG_DIR = user_config_dir(APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yml")


class Erwin:
    def __init__(self):
        self._first_boot = False
        self.master_fs = None
        self.slave_fs = None

    def do_load_config(self):
        try:
            with open(CONFIG_FILE, "r") as cf:
                self._config = yaml.safe_load(cf)
        except FileNotFoundError:
            self.do_initial_config()

    def do_initial_config(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)

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
            "\nBrilliant! Finally, I need the location of your credentals.json\n" "file"
        )

        creds_file = os.path.abspath(os.path.expanduser(input("> ")))

        aliased_creds_file = os.path.join(CONFIG_DIR, f"{alias}_credentials.json")
        copyfile(creds_file, aliased_creds_file)

        aliased_token_file = os.path.join(CONFIG_DIR, f"{alias}_token.pickle")

        print(
            "\nExcellent! That's all! I will now start synchronising your\n"
            "Google Drive files for you!"
        )

        self._config = {
            "alias": alias,
            "slave_fs": {"params": {"root": root}},
            "master_fs": {
                "params": {
                    "credentials": aliased_creds_file,
                    "token": aliased_token_file,
                }
            },
        }

        with open(CONFIG_FILE, "w") as cf:
            yaml.safe_dump(self._config, cf)

        self._first_boot = True

    def resolve_conflicts(self, master_deltas, slave_deltas):
        mc, sc = master_deltas.conflicts(slave_deltas)
        if mc or sc:
            LOGGER.info(f"Detected conflicts since last boot. Master: {mc}; Slave {sc}")

        def move_conflict(master_file, slave_file):
            conflict_path = self.slave_fs.conflict(slave_file)
            self.slave_fs.copy(slave_file, conflict_path)
            LOGGER.info(
                "Conflicting file on slave copied: "
                f"{master_file.path} -> {conflict_path}"
            )

        for file in [f for f in master_deltas.removed if f.path in sc]:
            move_conflict(file, self.slave_fs.search(file.path))

        for file in [f for f in master_deltas.new if f.path in sc]:
            slave_file = self.slave_fs.search(file.path)
            if slave_file and file.path in sc:
                # File is different, so slave file is conflict and we copy
                # master file over.
                move_conflict(file, slave_file)

        for src, dst in master_deltas.renamed:
            # src file has been moved/removed
            slave_src_file = self.slave_fs.search(src.path)

            if src.path in sc or not (src @ slave_src_file):
                # Conflict master -> slave
                move_conflict(src, slave_src_file)

            # dst file has been created/modi1fied
            slave_dst_file = self.slave_fs.search(dst.path)
            if not (dst @ slave_dst_file):
                if slave_dst_file and dst.path in sc:
                    # File is different, so slave file is conflict and we copy
                    # master file over.
                    move_conflict(dst, slave_dst_file)

    @staticmethod
    def apply_deltas(deltas, source, dest):
        source_fs, source_state = source
        dest_fs, dest_state = dest

        for file in deltas.removed:
            dest_file = dest_fs.search(file.path)

            if dest_file:
                dest_fs.remove(dest_file)

            if dest_state:
                dest_state.remove_file(file)
            if source_state:
                source_state.remove_file(file)

            LOGGER.debug(f"Removed {file}")

        for file in deltas.new:
            dest_file = dest_fs.search(file.path)

            if not (file & dest_file):
                if file.is_folder:
                    dest_fs.makedirs(file)
                else:
                    dest_fs.write(source_fs.read(file), file)
                    # Writing on a file requires two inotify events so we add
                    # an extra acquire
                while not (file & dest_file):
                    sleep(0.001)
                    dest_file = dest_fs.search(file.path)

            LOGGER.debug(f"Written {dest_file}")

            if dest_state:
                dest_state.add_file(dest_file)
            if source_state:
                source_state.add_file(file)

            if not file & dest_file:
                raise RuntimeError(
                    f"Source {file} and destination {dest_file} mismatch"
                )

            # LOGGER.debug(f"Created/modified {file}")

        for src, dst in deltas.renamed:
            # src file has been moved/removed
            dest_src_file = dest_fs.search(src.path)

            # dst file has been created/modi1fied
            dest_dst_file = dest_fs.search(dst.path)

            if dest_src_file:
                if src & dest_src_file:
                    dest_fs.move(src, dst.path)
                    if dest_state:
                        dest_state.move_file(dest_src_file, dst.path)
                else:
                    dest_fs.remove(dest_src_file)

            if not (dst & dest_dst_file):
                if dst.is_folder:
                    dest_fs.makedirs(dst)
                else:
                    dest_fs.write(source_fs.read(dst), dst)

            if dest_state:
                dest_state.add_file(dest_fs.search(dst.path))
                dest_state.remove_file(dest_src_file)

            if source_state:
                source_state.move_file(src, dst.path)

            LOGGER.debug(f"Renamed {src} -> {dst}")

    def do_init(self):
        # self.master_fs = GoogleDriveFS(**self._config["master_fs"]["params"])
        self.master_fs = LocalFS("/tmp/Downloads")
        LOGGER.debug(f"Created Master FS of type {type(self.master_fs)}")
        self.slave_fs = LocalFS(**self._config["slave_fs"]["params"])
        LOGGER.debug(f"Created Slave FS of type {type(self.slave_fs)}")

        master_state_file = os.path.join(
            CONFIG_DIR, f"{self._config['alias']}_master_state.pickle"
        )
        slave_state_file = os.path.join(
            CONFIG_DIR, f"{self._config['alias']}_slave_state.pickle"
        )

        # prev_master_state = GoogleDriveFSState.load(master_state_file)
        prev_master_state = LocalFSState.load(master_state_file)
        LOGGER.debug(f"Previous state of Master FS loaded")
        master_deltas = self.master_fs.get_state() - prev_master_state
        LOGGER.debug(f"Master deltas since last state save:\n{master_deltas}")

        prev_slave_state = LocalFSState.load(slave_state_file)
        LOGGER.debug("Previous state of Slave FS loaded")
        slave_deltas = self.slave_fs.get_state() - prev_slave_state
        LOGGER.debug(f"Slave deltas since last state save:\n{slave_deltas}")

        # register previou state handler with signals to gracefully shutdown
        # while in the middle of applying deltas

        def save_prev_states(signum=None, frame=None):
            prev_master_state.save(master_state_file)
            LOGGER.info("Master FS state saved")
            prev_slave_state.save(slave_state_file)
            LOGGER.info("Slave FS state saved")
            if signum:
                LOGGER.warn(f"Received termination signal ({signum}). Shutting down...")
                exit(signum)

        old_int_handler = signal.signal(signal.SIGINT, save_prev_states)
        old_term_handler = signal.signal(signal.SIGTERM, save_prev_states)

        try:
            self.resolve_conflicts(master_deltas, slave_deltas)

            Erwin.apply_deltas(
                master_deltas,
                (self.master_fs, prev_master_state),
                (self.slave_fs, prev_slave_state),
            )
            if self.master_fs.get_state() - prev_master_state:
                raise RuntimeError("Not all deltas applied correctly to master!")

            # At this point we do not expect to have any conflicts left as we
            # have resolved them at master before.
            new_slave_deltas = self.slave_fs.get_state() - prev_slave_state
            LOGGER.debug(f"New deltas: {new_slave_deltas}")

            Erwin.apply_deltas(
                new_slave_deltas,
                (self.slave_fs, prev_slave_state),
                (self.master_fs, prev_master_state),
            )

            def apply_changes(source, dest):
                for delta in source[0].get_changes():
                    Erwin.apply_deltas(delta, source, dest)

            watches = [
                threading.Thread(
                    target=apply_changes,
                    args=(
                        (self.master_fs, prev_master_state),
                        (self.slave_fs, prev_slave_state),
                    ),
                ),
                threading.Thread(
                    target=apply_changes,
                    args=(
                        (self.slave_fs, prev_slave_state),
                        (self.master_fs, prev_master_state),
                    ),
                ),
            ]

            for watch in watches:
                watch.daemon = True  # Kill with main thread
                watch.start()

            for watch in watches:
                watch.join()

        except Exception as e:
            LOGGER.critical(
                f"Emergency shutdown. Persisting the current FS states. Cause: {e}"
            )
            save_prev_states()
            raise e

        finally:
            LOGGER.debug("Restoring signal handlers")
            signal.signal(signal.SIGINT, old_int_handler)
            signal.signal(signal.SIGTERM, old_term_handler)

        save_prev_states()

    def do_sync(self):
        pass

    def start(self):
        self.do_load_config()
        self.do_init()
        self.do_sync()


def main():
    erwin = Erwin()
    erwin.start()


if __name__ == "__main__":
    main()
