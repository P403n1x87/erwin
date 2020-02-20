from collections import defaultdict
import datetime
from httplib2 import Http
import io
import mimetypes
import pickle
import os.path
from pprint import pprint as pp
from queue import Queue
from threading import RLock, Thread
from time import sleep

from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.http import HttpRequest, MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


from erwin.fs import Delta, File, FileSystem, State
from erwin.logging import LOGGER


STATE_LOCK = RLock()


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
    return file.get("mimeType", None) == "application/vnd.google-apps.folder"


class GoogleDriveFile(File):
    def __init__(self, path, md5, is_folder, modified_date, _id, mime_type, parents):
        super().__init__(path, md5, is_folder, modified_date)
        self._id = _id
        self.mime_type = mime_type
        self.parents = parents

    @property
    def id(self):
        return (
            (self._id, self.md5, self.modified_date)
            if not self.is_folder
            else (self._id, self.path)
        )


class GoogleDriveFSState(State):
    pass


class GoogleDriveFS(FileSystem):
    # If modifying these scopes, delete the file token.pickle.
    SCOPES = [
        "https://www.googleapis.com/auth/drive.appdata",
        "https://www.googleapis.com/auth/drive",
    ]

    FILE_FIELDS = [
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

    DIR_FIELDS = ["id", "name"]

    def __init__(self, credentials, token):
        self._drive = None
        self._changes_token = None
        self._state = None

        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(token):
            with open(token, "rb") as t:
                creds = pickle.load(t)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials, GoogleDriveFS.SCOPES
                )
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(token, "wb") as t:
                pickle.dump(creds, t)

        def build_request(http, *args, **kwargs):
            return

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

        self._droot = self._drive.files().get(fileId="root").execute()

        super().__init__(self._to_file(self._droot))

    def _to_file(self, df):
        is_folder = _is_folder(df)

        # cdate = df.get("createdTime", None)
        mdate = df.get("modifiedTime", None) if not is_folder else None

        return GoogleDriveFile(
            path=self._get_paths(df)[0].lstrip("/"),
            md5=df.get("md5Checksum", None),
            is_folder=is_folder,
            # created_date=datetime.datetime.strptime(cdate, "%Y-%m-%dT%H:%M:%S.%fZ")
            # if cdate
            # else None,
            modified_date=datetime.datetime.strptime(mdate, "%Y-%m-%dT%H:%M:%S.%fZ")
            if mdate
            else None,
            _id=df["id"],
            mime_type=df["mimeType"],
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
        while True:
            LOGGER.debug("Getting Drive changes")
            new_state = GoogleDriveFSState.from_file_list(self.list(recursive=True))
            yield new_state - self._state
            with STATE_LOCK:
                self._state = new_state
            sleep(5)

    def get_state(self):
        if self._state:
            return self._state

        self._state = GoogleDriveFSState.from_file_list(self.list(recursive=True))
        return self._state

    def search(self, path):
        with STATE_LOCK:
            return self.get_state()[path]

    def list(self, recursive=False):
        parent = self.root

        query = "trashed = false"
        if not recursive:
            query += f" and '{parent._id}' in parents"

        file_list, _ = _all_pages(
            self._drive.files,
            q=query,
            fields=f"nextPageToken, files({','.join(GoogleDriveFS.FILE_FIELDS)})",
        )

        # if not recursive:
        #     return file_list

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

        return [self.root] + [
            f
            for f in [self._to_file(file) for file in sorted_list]
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

    def read(self, file: GoogleDriveFile):
        LOGGER.info(f"Downloading {file}")
        try:
            request = self._drive.files().get_media(fileId=file._id)
            stream = io.BytesIO()
            self._download(request, stream)
        except HttpError as e:
            LOGGER.error(f"Error reading {file}. Cause: {e}")
            # Export a Google Doc file
            if e.resp.status == 403:
                pass
                # try:
                #     self._download(
                #         self._drive.files().export_media(
                #             fileId=file.id, mimeType=file.mime_type
                #         ),
                #         stream,
                #     )
                # except HttpError as f:
                #     if e.resp.status != 403:
                #         raise

        # print("Download %d%%." % int(status.progress() * 100), end="\r")

        stream.flush()
        stream.seek(0)

        return stream

    def makedirs(self, path):
        def splitdirs(path):
            if path in ("", "/"):
                return []
            head, _ = os.path.split(path)
            return splitdirs(head) + [path]

        def makedir(name, parent):
            file_metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent._id],
            }
            folder = self._to_file(
                self._drive.files()
                .create(body=file_metadata, fields=",".join(GoogleDriveFS.DIR_FIELDS))
                .execute()
            )

            with STATE_LOCK:
                self.get_state().add_file(folder)

            return folder

        root, *dirs = splitdirs(path)
        parent = self.search(root)
        if not parent:
            raise RuntimeError("Invalid path")
        for p in dirs:
            parent = self.search(p) or makedir(os.path.split(p)[1], parent)

    def remove(self, file):
        self._drive.files().update(fileId=file._id, body={"trashed": True}).execute()
        with STATE_LOCK:
            self.get_state().remove_file(file)

    def write(self, stream, file):
        current_file = self.search(file.path)
        if current_file:  # A file exists at this location
            if not file & current_file:  # File content doesn't match
                new_file = self._to_file(
                    self._drive.files()
                    .update(
                        fileId=current_file._id,
                        body={
                            "name": os.path.basename(file.path),
                            "modifiedTime": datetime.datetime.strftime(
                                file.modified_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                            ),
                        },
                        media_body=MediaIoBaseUpload(
                            stream,
                            mimetype=mimetypes.guess_type(file.path)[0]
                            or "application/octet-stream",
                        ),
                        fields=",".join(GoogleDriveFS.FILE_FIELDS),
                    )
                    .execute()
                )
            else:
                new_file = current_file
        else:
            # File does not exist, create it
            new_file = self._to_file(
                self._drive.files()
                .create(
                    body={
                        "name": os.path.basename(file.path),
                        "modifiedTime": datetime.datetime.strftime(
                            file.modified_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                        ),
                    },
                    media_body=MediaIoBaseUpload(
                        stream,
                        mimetype=mimetypes.guess_type(file.path)[0]
                        or "application/octet-stream",
                    ),
                    fields=",".join(GoogleDriveFS.FILE_FIELDS),
                )
                .execute()
            )

        if new_file != current_file:
            with STATE_LOCK:
                self.get_state().add_file(new_file)

    def conflict(self, file):
        # Not required for a master FS.
        pass

    def copy(self, file, dst):
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
                        file.modified_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                    ),
                    "parents": [dst_dir._id],
                },
            )
            .execute()
        )

        with STATE_LOCK:
            self.get_state().add_file(copy)

    def move(self, file, dst):
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
            )
            .execute()
        )

        with STATE_LOCK:
            state = self.get_state()
            state.remove_file(file)
            state.add_file(dest_file)


def print_tree(tree, level=0):
    print("  " * level + tree["file"]["name"])
    for child in tree["children"]:
        print_tree(child, level=level + 1)
