from appdirs import user_config_dir

from enum import Enum, auto
import os.path
from shutil import copyfile
import yaml

from erwin.fs import FileSystem
from erwin.fs.drive import GoogleDriveFS, GoogleDriveFSState
from erwin.fs.local import LocalFS, LocalFSState


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

    def apply_deltas(self, master_deltas, slave_deltas):
        master_state = GoogleDriveFSState()

        for file in sorted(master_deltas.removed, key=lambda x: x.path):
            master_state.remove_file(file)
            self.slave_fs.remove(file)

    def do_first_boot(self):
        # Download from master FS and rename any conflicts on slave
        for file in sorted(self.master_fs.list(recursive=True), key=lambda f: f.path):
            dest_file = self.slave_fs.search(file)

            if file @ dest_file:
                continue

            if dest_file:  # Conflict
                self.slave_fs.move(dest_file, dest_file.path + " (conflicted copy)")

            if file.is_folder:
                self.slave_fs.makedirs(file.path)
            else:
                self.master_fs.read(file, self.slave_fs.write(file))

        # Upload from slave
        for file in sorted(self.slave_fs.list(recursive=True), key=lambda f: f.path):
            dest_file = self.master_fs.search(file.path)

            if dest_file:
                continue

            if file.is_folder:
                self.master_fs.makedirs(file.path)
            else:
                self.slave_fs.read(file, self.master_fs.write(file))

    def do_init(self):
        self.master_fs = GoogleDriveFS(**self._config["master_fs"]["params"])
        self.slave_fs = LocalFS(**self._config["slave_fs"]["params"])

        if self._first_boot:
            self.do_first_boot()

        master_state_file = os.path.join(
            CONFIG_DIR, f"{self._config['alias']}_master_state.pickle"
        )
        slave_state_file = os.path.join(
            CONFIG_DIR, f"{self._config['alias']}_slave_state.pickle"
        )

        prev_master_state = GoogleDriveFSState.load(master_state_file)
        master_deltas = self.master_fs.get_state() - prev_master_state
        # print("Master changes")
        # print(str(master_deltas))

        # self.master_fs.get_state().save(master_state_file)

        # On first ever boot we know we need to download files from remote to
        # local. Check if we already have the same file to save some bandwidth.
        # For each conflict, rename the local file and download the remote one.
        # After that check if there are extra local files (including
        # conflicting copies!) that are not in the remotelocation and push
        # those upstream.

        prev_slave_state = LocalFSState.load(slave_state_file)
        slave_deltas = self.slave_fs.get_state() - prev_slave_state
        # print("Slave Changes")
        # print(str(slave_deltas))

        # self.slave_fs.get_state().save(slave_state_file)

        mc, sc = master_deltas.conflicts(slave_deltas)

        for file in master_deltas.removed:
            slave_file = self.slave_fs.search(file.path)
            if file.path in sc:
                # Conflict master -> slave
                conflict_file_path = "conflict_" + file.path
                self.slave_fs.move(slave_file, conflict_file_path)
                prev_slave_state.add_file(slave_file)
            else:
                self.slave_fs.remove(slave_file)

        for file in master_deltas.new:
            if file.path in mc & sc:
                # the file is being created/modified on both ends
                pass
            elif file.path in mc - sc:
                # the file is being removed/moved by slave
                pass
            else:
                # conflicts
                pass

        for src, dst in master_deltas.renamed:
            pass

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
