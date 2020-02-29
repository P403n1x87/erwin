from queue import Queue
from shutil import copyfile
import threading
from time import sleep

# from time import sleep

from erwin.config import ErwinConfiguration
from erwin.flow import backoff
from erwin.fs.drive import GoogleDriveFS
from erwin.fs.local import LocalFS
from erwin.logging import LOGGER


class Erwin:
    def __init__(self):
        self.master_fs = None
        self.slave_fs = None
        self._queue = Queue()  # Queue of collected deltas

    def resolve_conflicts(self, master_deltas, slave_deltas):
        mc, sc = master_deltas & slave_deltas
        if mc or sc:
            LOGGER.info(f"Detected conflicts since last boot. Master: {mc}; Slave {sc}")

        def move_conflict(path):
            conflict_path = self.slave_fs.conflict(path)
            self.slave_fs.copy(path, conflict_path)
            LOGGER.info(
                "Conflicting file on slave copied: " f"{path} -> {conflict_path}"
            )

        for path in [p for p in master_deltas.removed if p in sc]:
            move_conflict(path)

        for path in [p for p in master_deltas.added if p in sc]:
            master_file = self.slave_fs.search(path)
            if not master_file:
                raise RuntimeError("Master file is unexpectedly missing.")
            slave_file = self.slave_fs.search(path)
            if slave_file and path in sc and not master_file & slave_file:
                # File is different, so slave file is conflict and we copy
                # master file over.
                move_conflict(path)

        for src, dst in master_deltas.moved:
            # src file has been moved/removed
            slave_src_file = self.slave_fs.search(src)

            if slave_src_file and src in sc:
                # Conflict master -> slave
                move_conflict(src)

            # dst file has been created/modified
            master_dst_file = self.master_fs.search(dst)
            if not master_dst_file:
                raise RuntimeError("Master file is unexpectedly missing.")
            slave_dst_file = self.slave_fs.search(dst)
            if slave_dst_file and dst in sc and not (master_dst_file & slave_dst_file):
                # File is different, so slave file is conflict and we copy
                # master file over.
                move_conflict(dst)

    def _start_collectors(self, master_state, slave_state):
        def collect_deltas(source, dest):
            for delta in source[0].get_changes():
                if delta:
                    LOGGER.debug(
                        f"Incremental delta received from {source[0]}:\n{delta}"
                    )
                    self._queue.put((delta, source, dest))

        LOGGER.info("Watching for FS state changes")

        watches = [
            threading.Thread(
                name="Watch-MS",
                target=collect_deltas,
                args=((self.master_fs, master_state), (self.slave_fs, slave_state)),
            ),
            threading.Thread(
                name="Watch-SM",
                target=collect_deltas,
                args=((self.slave_fs, slave_state), (self.master_fs, master_state)),
            ),
        ]

        for watch in watches:
            watch.daemon = True  # Kill with main thread
            watch.start()

        while True:
            delta, source, dest = self._queue.get()
            delta.apply(source, dest)
            LOGGER.debug(f"Incremental delta applied to {dest[0]}")

        for watch in watches:
            watch.join()

    @backoff(delay=5, ratio=1.618, cap=60)
    def start(self):
        with ErwinConfiguration() as config:
            LOGGER.info("Erwin configuration loaded successfully.")

            # Create master and slave FSs
            self.master_fs = GoogleDriveFS(**config.get_master_fs_params())
            LOGGER.info("Master FS is online.")
            LOGGER.debug(f"Created Master FS of type {type(self.master_fs)}")

            self.slave_fs = LocalFS(**config.get_slave_fs_params())
            LOGGER.info("Slave FS is online.")
            LOGGER.debug(f"Created Slave FS of type {type(self.slave_fs)}")

            # Load the previous state
            prev_master_state, prev_slave_state = config.load_fs_states()

            # Register signal handlers
            config.register_state_handler(prev_master_state, prev_slave_state)

            LOGGER.info("Previous FS states loaded successfully.")

            # Compute deltas since last launch
            master_deltas = self.master_fs.state - prev_master_state
            LOGGER.debug(f"Master deltas since last state save:\n{master_deltas}")

            slave_deltas = self.slave_fs.state - prev_slave_state
            LOGGER.debug(f"Slave deltas since last state save:\n{slave_deltas}")

            self.resolve_conflicts(master_deltas, slave_deltas)

            master_deltas.apply(
                (self.master_fs, prev_master_state), (self.slave_fs, prev_slave_state)
            )
            if self.master_fs.state - prev_master_state:
                raise RuntimeError("Not all deltas applied correctly to master!")

            # At this point we do not expect to have any conflicts left as we
            # have resolved them at master before.
            new_slave_deltas = self.slave_fs.state - prev_slave_state
            LOGGER.debug(f"New deltas:\n{new_slave_deltas}")

            new_slave_deltas.apply(
                (self.slave_fs, prev_slave_state), (self.master_fs, prev_master_state)
            )

            # Start the collectors to watch for changes on both FSs.
            self._start_collectors(prev_master_state, prev_slave_state)


def main():
    Erwin().start()


if __name__ == "__main__":
    main()
