from collections import defaultdict
import datetime
from httplib2 import Http, ServerNotFoundError
import io
import mimetypes
import pickle
import os.path
from pprint import pprint as pp
from queue import Queue
from threading import Event, RLock, Thread
from time import sleep

from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.http import HttpRequest, MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


from erwin.fs import Delta, File, FileSystem, FSNotReady, State
from erwin.logging import LOGGER


STATE_LOCK = RLock()
CONNECTED = Event()


def suppresserror(f):
    def wrapper(*args, **kwargs):
        try:
            CONNECTED.wait()
            return f(*args, **kwargs)
        except HttpError as e:
            if e.resp.status == 403:
                LOGGER.warning(
                    f"HTTP error suppressed after call to {f} with arguments "
                    f"{args}, {kwargs}: {e}"
                )
            else:
                raise e
        except ServerNotFoundError as e:
            LOGGER.error(
                f"Cannot call {f} with arguments {args}, {kwargs} at this time. "
                f"Reason: {e}"
            )
            CONNECTED.clear()
            CONNECTED.wait()
            return suppresserror(f)(*args, **kwargs)

    return wrapper


def _all_pages(method, token=None, **kwargs):
    retval = []
    token = token
    while True:
        result = method().list(pageSize=1000, pageToken=token, **kwargs).execute()
        (collection,) = [
            k
            for k in result.keys()
            if k
            not in ["kind", "nextPageToken", "incompleteSearch", "newStartPageToken"]
        ]
        retval += result.get(collection, [])
        token = result.get("nextPageToken", None)
        if not token:
            break

    return retval, result.get("newStartPageToken", None)


def _children_map(object_list):
    children_map = defaultdict(list)

    for o in object_list:
        for p in o.get("parents", []):
            children_map[p].append(o)

    return children_map


def _is_folder(file):
    return file.get("mimeType", None) == GoogleDriveFS.FOLDER_MIMETYPE


class GoogleDriveFile(File):
    def __init__(self, md5, is_folder, modified_date, _id, mime_type, parents):
        super().__init__(md5, is_folder, modified_date)
        self._id = _id
        self.mime_type = mime_type
        self.parents = parents

    @property
    def id(self):
        return self._id, self.md5, self.modified_date


class GoogleDriveFSState(State):
    pass


class GoogleDriveFS(FileSystem):
    DEFAULT_MIMETYPE = "application/octet-stream"
    FOLDER_MIMETYPE = "application/vnd.google-apps.folder"

    CLIENT_CONFIG = {
        "installed": {
            "client_id": "261427220234-n82d3mi8flk88u8s25l8lc8gau7ej6g9.apps.googleusercontent.com",
            "project_id": "erwin-sync",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "3QwRSY0B0On8TIeCnsEN7X50",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    SCOPES = [
        "https://www.googleapis.com/auth/drive.appdata",
        "https://www.googleapis.com/auth/drive",
    ]

    FILE_FIELDS = ",".join(
        [
            "mimeType",
            "trashed",
            "id",
            # "capabilities",
            "parents",
            "fullFileExtension",
            "originalFilename",
            "modifiedTime",
            "createdTime",
            "md5Checksum",
            "name",
            "exportLinks",
            # "driveId",
            # "spaces",
            # "headRevisionId",
        ]
    )

    DIR_FIELDS = ",".join(["id", "name", "mimeType", "parents"])

    def __init__(self, token):
        self._drive = None
        self._changes_token = None
        self._state = None

        creds = None

        if os.path.exists(token):
            with open(token, "rb") as t:
                creds = pickle.load(t)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_config(
                    GoogleDriveFS.CLIENT_CONFIG, GoogleDriveFS.SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(token, "wb") as t:
                pickle.dump(creds, t)

        try:
            self._drive = build(
                "drive",
                "v3",
                credentials=creds,
                cache_discovery=False,
                # Create a new instance of Http to make the Google API thread-safe
                # See https://github.com/googleapis/google-api-python-client/blob/master/docs/thread_safety.md
                requestBuilder=lambda _, *args, **kwargs: HttpRequest(
                    AuthorizedHttp(creds, http=Http()), *args, **kwargs
                ),
            )
        except ServerNotFoundError as e:
            raise FSNotReady("The Google Drive API is unreachable") from e

        CONNECTED.set()

        self._droot = self._drive.files().get(fileId="root").execute()

        super().__init__(self._to_file(self._droot))

    def _to_file(self, df):
        is_folder = _is_folder(df)

        mdate = df.get("modifiedTime", None) if not is_folder else None

        return GoogleDriveFile(
            md5=df.get("md5Checksum", None) if not is_folder else self._path(df),
            is_folder=is_folder,
            modified_date=datetime.datetime.strptime(mdate, "%Y-%m-%dT%H:%M:%S.%fZ")
            if mdate
            else None,
            _id=df["id"],
            mime_type=self.FOLDER_MIMETYPE
            if is_folder
            else df.get("mimeType", self.DEFAULT_MIMETYPE),
            parents=df.get("parents", []),
        )

    def _get_paths(self, file, partial_path="", path_list=None):
        if path_list is None:
            path_list = []

        partial_path = "/" + file["name"] + partial_path

        parents = file.get("parents", [])
        if not parents:
            path_list.append(partial_path)
            return path_list

        for parent in parents:
            self._get_paths(self._file_map[parent], partial_path, path_list)

        return path_list

    def _path(self, df):
        return self._get_paths(df)[0].lstrip("/")

    def list_shared_drives(self):
        return self._drive.drives().list().execute().get("drives", [])

    def _list_all(self):
        return _all_pages(self._drive.files, fields="*")[0]

    def tree(self, parent=None):
        parent = parent or self.get_root()
        children_map = _children_map(self._list_all())

        def get_children(file):
            return [
                {"file": child, "children": get_children(child)}
                for child in children_map[file["id"]]
            ]

        return {"file": parent, "children": get_children(parent)}

    def _get_changes(self):
        start_token = self._changes_token or (
            self._drive.changes()
            .getStartPageToken()
            .execute()
            .get("startPageToken", None)
        )
        if not start_token:
            return []

        changes, self._changes_token = _all_pages(
            self._drive.changes, token=start_token, includeRemoved=True
        )

        return changes

    def get_file(self, _id):
        try:
            return self._to_file(
                self._drive.files()
                .get(fileId=_id, fields=",".join(self.FILE_FIELDS))
                .execute()
            )
        except HttpError:
            return None

    def get_changes(self):
        backoff = 10
        while True:
            LOGGER.debug("Getting Drive changes")
            try:
                new_state = GoogleDriveFSState.from_file_list(self.list())
                backoff = 10
                CONNECTED.set()

                yield new_state - self._state

                with STATE_LOCK:
                    self._state = new_state

            except ServerNotFoundError:
                backoff *= 1.618
                LOGGER.error(
                    f"The Google Drive API is unreachable. Retrying in {int(backoff)} seconds."
                )

            finally:
                sleep(backoff)

    @property
    def state(self):
        if self._state:
            return self._state

        self._state = GoogleDriveFSState.from_file_list(self.list())
        return self._state

    def search(self, path):
        with STATE_LOCK:
            return self.state[path]

    def list(self):
        parent = self.root

        query = "trashed = false"
        # if not recursive:
        #     query += f" and '{parent._id}' in parents"

        file_list, _ = _all_pages(
            self._drive.files,
            q=query,
            fields=f"nextPageToken, files({GoogleDriveFS.FILE_FIELDS})",
        )

        self._file_map = {f["id"]: f for f in file_list}
        self._file_map[self._droot["id"]] = self._droot

        file_list = [f for f in file_list if not f.get("exportLinks", None)]

        sorted_list = []
        children_map = _children_map(file_list)

        def add_children(p):
            for child in children_map[p["id"]]:
                sorted_list.append(child)
                add_children(child)

        add_children(self._droot)

        # TODO return path, file pairs
        return [(self._path(self._droot), self.root)] + [
            (p, f)
            for f, p in [
                (self._to_file(file), self._path(file)) for file in sorted_list
            ]
            if f.is_folder or f.md5
        ]

        # q="mimeType = 'application/vnd.google-apps.folder'",

    def _download(self, request, buffer):
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while done is False:
            try:
                status, done = downloader.next_chunk()
            except HttpError as e:
                if e.resp.status == 416:
                    break
                raise
        return buffer

    @suppresserror
    def read(self, path):
        file = self.search(path)
        if not file:
            raise FileNotFoundError(path)

        LOGGER.info(f"Downloading {file}")

        request = self._drive.files().get_media(fileId=file._id)
        stream = io.BytesIO()
        self._download(request, stream)

        # TODO: This code should be fixed in order to support Google Docs
        #
        # except HttpError as e:
        #     LOGGER.error(f"Error reading {file}. Cause: {e}")
        #     # Export a Google Doc file
        #     if e.resp.status == 403:
        #         pass
        #         try:
        #             self._download(
        #                 self._drive.files().export_media(
        #                     fileId=file.id, mimeType=file.mime_type
        #                 ),
        #                 stream,
        #             )
        #         except HttpError as f:
        #             if e.resp.status != 403:
        #                 raise

        stream.flush()
        stream.seek(0)

        return stream

    @suppresserror
    def makedirs(self, path):
        def splitdirs(path):
            if path in ("", "/"):
                return []
            head, _ = os.path.split(path)
            return splitdirs(head) + [path]

        def makedir(path, parent):
            _, name = os.path.split(p)
            file_metadata = {
                "name": name,
                "mimeType": self.FOLDER_MIMETYPE,
                "parents": [parent._id],
            }
            folder = self._to_file(
                self._drive.files()
                .create(body=file_metadata, fields=GoogleDriveFS.DIR_FIELDS)
                .execute()
            )

            with STATE_LOCK:
                self.state.add(folder, path)

            return folder

        root, *dirs = splitdirs(path)
        parent = self.search(root)
        if not parent:
            raise RuntimeError("Invalid path")
        for p in dirs:
            parent = self.search(p) or makedir(p, parent)

    @suppresserror
    def remove(self, path):
        file = self.search(path)
        if not file:
            return

        self._drive.files().update(fileId=file._id, body={"trashed": True}).execute()
        with STATE_LOCK:
            self.state.remove(path)

    @suppresserror
    def write(self, stream, path, modified_date):
        current_file = self.search(path)
        if current_file:  # A file exists at this location
            new_file = self._to_file(
                self._drive.files()
                .update(
                    fileId=current_file._id,
                    body={
                        "name": os.path.basename(path),
                        "modifiedTime": datetime.datetime.strftime(
                            modified_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                        ),
                    },
                    media_body=MediaIoBaseUpload(
                        stream,
                        mimetype=mimetypes.guess_type(path)[0] or self.DEFAULT_MIMETYPE,
                    ),
                    fields=GoogleDriveFS.FILE_FIELDS,
                )
                .execute()
            )
        else:  # File does not exist, create it
            folder, name = os.path.split(path)
            parent = self.search(folder)
            if not parent:
                raise RuntimeError("Destination folder does not exist.")

            new_file = self._to_file(
                self._drive.files()
                .create(
                    body={
                        "name": name,
                        "modifiedTime": datetime.datetime.strftime(
                            modified_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                        ),
                        "parents": [parent._id],
                    },
                    media_body=MediaIoBaseUpload(
                        stream,
                        mimetype=mimetypes.guess_type(name)[0] or self.DEFAULT_MIMETYPE,
                    ),
                    fields=GoogleDriveFS.FILE_FIELDS,
                )
                .execute()
            )

        with STATE_LOCK:
            self.state.add(new_file, path)

    def conflict(self, file):
        # Not required for a master FS.
        pass

    @suppresserror
    def copy(self, src, dst):
        file = self.search(src)
        if not file:
            return

        head, tail = os.path.split(dst)
        dst_dir = self.search(head)
        if not dst_dir:
            raise RuntimeError("Destination folder does not exist.")

        copy = self._to_file(
            self._drive.files()
            .copy(
                fileId=file._id,
                body={
                    "name": tail,
                    "modifiedTime": datetime.datetime.strftime(
                        modified_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                    ),
                    "parents": [dst_dir._id],
                },
                fields=GoogleDriveFS.FILE_FIELDS,
            )
            .execute()
        )

        with STATE_LOCK:
            self.state.add(copy, dst)

    @suppresserror
    def move(self, src, dst):
        file = self.search(src)
        if not file:
            return

        head, tail = os.path.split(dst)
        dst_dir = self.search(head)
        if not dst_dir:
            raise RuntimeError("Destination folder does not exist.")

        dest_file = self._to_file(
            self._drive.files()
            .update(
                fileId=file._id,
                body={"name": tail},
                addParents=dst_dir._id,
                removeParents=",".join(file.parents),
                fields=GoogleDriveFS.FILE_FIELDS,
            )
            .execute()
        )

        with STATE_LOCK:
            state = self.state
            state.remove(src)
            state.add(dest_file, dst)
