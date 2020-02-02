from appdirs import user_config_dir

from enum import Enum, auto
import os.path
import signal
from shutil import copyfile
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

    def do_init(self):
        # self.master_fs = GoogleDriveFS(**self._config["master_fs"]["params"])
        self.master_fs = LocalFS(root="/tmp/Downloads")
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
        # print("Master changes")
        # print(str(master_deltas))

        # self.master_fs.get_state().save(master_state_file)

        prev_slave_state = LocalFSState.load(slave_state_file)
        LOGGER.debug("Previous state of Slave FS loaded")
        slave_deltas = self.slave_fs.get_state() - prev_slave_state
        LOGGER.debug(f"Slave deltas since last state save:\n{slave_deltas}")
        # print("Slave Changes")
        # print(str(slave_deltas))

        # self.slave_fs.get_state().save(slave_state_file)

        mc, sc = master_deltas.conflicts(slave_deltas)
        if mc or sc:
            LOGGER.info(f"Detected conflicts since last boot. Master: {mc}; Slave {sc}")

        # register previou state handler with signals to gracefully shutdown
        # while in the middle of applying deltas

        def save_prev_states(signum=None, frame=None):
            prev_master_state.save(master_state_file)
            LOGGER.info("Master FS state saved")
            prev_slave_state.save(slave_state_file)
            LOGGER.info("Slave FS state saved")

        old_int_handler = signal.signal(signal.SIGINT, save_prev_states)
        old_term_handler = signal.signal(signal.SIGTERM, save_prev_states)

        def move_conflict(master_file, slave_file):
            conflict_file_path = "conflict_" + file.path
            self.slave_fs.move(slave_file, conflict_file_path)
            LOGGER.info(
                "Conflicting file on slave ranamed:"
                f"{master_file.path} -> {conflict_file_path}"
            )

        try:
            for file in master_deltas.removed:
                slave_file = self.slave_fs.search(file.path)

                if file.path in sc:  # Conflict master -> slave
                    move_conflict(file, slave_file)
                elif slave_file:
                    self.slave_fs.remove(slave_file)

                if slave_file:
                    prev_slave_state.remove_file(slave_file)
                prev_master_state.remove_file(file)
                LOGGER.debug(f"Master removed file {file.path}")

            for file in master_deltas.new:
                slave_file = self.slave_fs.search(file.path)
                if not (file @ slave_file):
                    if slave_file and file.path in mc & sc:
                        # File is different, so slave file is conflict and we copy
                        # master file over.
                        move_conflict(file, slave_file)
                    self.slave_fs.write(self.master_fs.read(file), file)
                prev_slave_state.add_file(self.slave_fs.search(file.path))
                prev_master_state.add_file(file)
                LOGGER.debug(f"Master created/modified {file.path}")

            for src, dst in master_deltas.renamed:
                # src file has been moved/removed
                slave_src_file = self.slave_fs.search(src.path)

                if src.path in sc or not (src @ slave_src_file):
                    # Conflict master -> slave
                    move_conflict(src, slave_src_file)

                # dst file has been created/modi1fied
                slave_dst_file = self.slave_fs.search(dst.path)
                if not (dst @ slave_dst_file):
                    if slave_dst_file and dst.path in mc & sc:
                        # File is different, so slave file is conflict and we copy
                        # master file over.
                        move_conflict(dst, slave_dst_file)

                if slave_src_file:
                    if src @ slave_src_file:
                        self.slave_fs.move(src, dst.path)
                        prev_slave_state.rename_file(prev_src_file, dst.path)
                    else:
                        self.slave_fs.remove(slave_src_file)
                        prev_slave_state.remove_file(slave_src_file)
                        if not slave_dst_file:
                            self.slave_fs.write(self.master_fs.read(dst), dst)
                            slave_dst_file = self.slave_fs.search(dst.path)
                            prev_slave_state.add_file(slave_dst_file)
                else:
                    if not slave_dst_file or not dst @ slave_dst_file:
                        self.slave_fs.write(self.master_fs.read(dst), dst)
                        prev_slave_state.add_file(self.slave_fs.search(dst.path))

                prev_master_state.rename_file(src, dst.path)
                LOGGER.debug(f"Master renamed {src.path} -> {dst.path}")

            # Get new slave deltas and apply them to master. As a sanity check,
            # make sure there are no conflicts in this last step.

            new_slave_deltas = self.slave_fs.get_state() - prev_slave_state
            mc, sc = master_deltas.conflicts(new_slave_deltas)
            if mc or sc:
                raise RuntimeError("Conflicts after master delta merges.")

            for file in new_slave_deltas.new:
                self.master_fs.write(self.slave_fs.read(file), file)
                prev_master_state.add_file(self.master_fs.search(file.path))
                prev_slave_state.add_file(file)
                LOGGER.debug(f"Slave created/modified {file.path}")
            for file in new_slave_deltas.removed:
                master_file = self.master_fs.search(file.path)
                if master_file:
                    self.master_fs.remove(master_file)
                    prev_master_state.remove_file(master_file)
                prev_slave_state.remove_file(file)
                LOGGER.debug(f"Slave removed {file.path}")
            for src, dst in new_slave_deltas.renamed:
                LOGGER.debug(f"WIP!! Slave moved {src.path} -> {dst.path}")
                # TODO: WIP

        finally:
            signal.signal(signal.SIGINT, old_int_handler)
            signal.signal(signal.SIGTERM, old_term_handler)

        save_prev_states()
        # print(mc, sc)

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
