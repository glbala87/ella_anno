import boto3
import os
from pathlib import Path
import sys
import threading


SPACES_REGION = "fra1"
SPACES_ENDPOINT = f"https://{SPACES_REGION}.digitaloceanspaces.com"
SPACES_BUCKET = "ella-anno"
ROOT_DIR = Path(__file__).absolute().parent.parent
DATA_DIR = ROOT_DIR / "data"


class DataManager(object):
    _bucket = None
    _client = None
    _s3 = None
    _session = None

    def __init__(self, access_key=None, access_secret=None, **kwargs):
        self.access_key = os.environ.get("DO_ACCESS_KEY", access_key)
        if self.access_key is None:
            raise ValueError("You must include either access_key param or DO_ACCESS_KEY environent variable")

        self.access_secret = os.environ.get("DO_ACCESS_SECRET", access_secret)
        if self.access_secret is None:
            raise ValueError("You must include either access_secret param or DO_ACCESS_SECRET environent variable")

    @property
    def client(self):
        if self._client is None:
            self._client = self.session.client(
                "s3",
                region_name=SPACES_REGION,
                endpoint_url=SPACES_ENDPOINT,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.access_secret,
            )

        return self._client

    @property
    def bucket(self):
        if self._bucket is None:
            self._bucket = self.s3.Bucket(SPACES_BUCKET)

        return self._bucket

    @property
    def s3(self):
        if self._s3 is None:
            self._s3 = boto3.resource("s3")

        return self._s3

    @property
    def session(self):
        if self._session is None:
            self._session = boto3.session.Session()

        return self._session

    def upload_package(self, name, version, path, extra={}):
        abs_path = path.absolute()
        key_base = f"data/{name}/{version}"
        if not path.exists():
            raise ValueError(f"Nothing exists at path: {path}")
        if path.is_dir():
            package_files = path.rglob("*")
        else:
            package_files = [path]

        for file_obj in package_files:
            if file_obj.is_absolute():
                file_key = f"{file_obj.relative_to(abs_path)}"
            else:
                file_key = f"{file_obj.absolute().relative_to(abs_path)}"
            spaces_key = f"{key_base}/{file_key}"

            print(f"Now uploading {file_key} to {spaces_key}")
            self.client.upload_fileobj(file_obj.open("rb"), SPACES_BUCKET, spaces_key, ExtraArgs=extra)

    def download_package(self, name, version):
        pass

    def check_package(self, name, version):
        pass


class ProgressPercentage(object):
    """Prints progress of a file transfer"""

    def __init__(self, file_obj):
        if type(file_obj) is Path:
            pass
        elif type(file_obj) is S3Object:
            pass
        self._filename = file_obj.name
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        # To simplify, assume this is hooked up to a single filename
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            sys.stdout.write("\r%s  %s / %s  (%.2f%%)" % (self._filename, self._seen_so_far, self._size, percentage))
            sys.stdout.flush()


def walk_path(path_obj, ignore=[]):
    files = list()
    if path_obj.is_dir():
        for file_obj in path_obj.iterdir():
            if file_obj.is_dir():
                walk_path(file_obj)
            elif file_obj.name not in ignore:
                files.append(file_obj)

    return files
