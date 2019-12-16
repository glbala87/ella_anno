import boto3
from botocore.exceptions import ClientError
from botocore.handlers import disable_signing
import csv
from collections import namedtuple
import os
from pathlib import Path, PosixPath
import sys
import threading


SPACES_REGION = "fra1"
SPACES_ENDPOINT = f"https://{SPACES_REGION}.digitaloceanspaces.com"
SPACES_BUCKET = "ella-anno"
ROOT_DIR = Path(__file__).absolute().parent.parent
DATA_DIR = ROOT_DIR / "data"
S3Object = type(boto3.resource("s3").Object("", ""))
PackageFile = namedtuple("PackageFile", ["local", "remote"])


def s3_object_exists(s3_object):
    try:
        s3_object.load()
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise e
    return True


def files_match(local_obj, remote_obj):
    return s3_object_exists(remote_obj) and local_obj.exists() and local_obj.stat().st_size == remote_obj.content_length


class DataManager(object):
    _bucket = None
    _client = None
    _s3 = None
    _session = None

    def __init__(self, access_key=None, access_secret=None, **kwargs):
        self.access_key = os.environ.get("SPACES_KEY", access_key)
        self.access_secret = os.environ.get("SPACES_SECRET", access_secret)
        self.region = kwargs.get("region_name", SPACES_REGION)
        self.endpoint = kwargs.get("endpoint_url", SPACES_ENDPOINT)

    @property
    def client(self):
        if self._client is None:
            self._client = self.session.client("s3", endpoint_url=self.endpoint)

        return self._client

    @property
    def bucket(self):
        if self._bucket is None:
            self._bucket = self.s3.Bucket(SPACES_BUCKET)

        return self._bucket

    @property
    def s3(self):
        if self._s3 is None:
            if self.access_key is None or self.access_secret is None:
                # no key/secret needed for downloading data, so if they're not found we can assume that
                # Will instead crash on missing creds with session creation
                self._s3 = boto3.resource("s3", region_name=self.region, endpoint_url=self.endpoint)
                # BUT attempting to sign without key/secret causes errors, so let's not do that
                self._s3.meta.client.meta.events.register("choose-signer.s3.*", disable_signing)
            else:
                self._s3 = boto3.resource(
                    "s3",
                    region_name=self.region,
                    endpoint_url=self.endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.access_secret,
                )

        return self._s3

    @property
    def session(self):
        if self._session is None:
            if self.access_key is None:
                raise ValueError("You must include either access_key param or SPACES_KEY environent variable")

            if self.access_secret is None:
                raise ValueError("You must include either access_secret param or SPACES_SECRET environent variable")

            self._session = boto3.session.Session(
                region_name=self.region, aws_access_key_id=self.access_key, aws_secret_access_key=self.access_secret
            )

        return self._session

    def upload_package(self, name, version, path):
        abs_path = path.absolute()
        key_base = f"data/{name}/{version}"

        package_files = []
        if not path.exists():
            raise ValueError(f"Nothing exists at path: {path}")
        elif path.is_dir():
            for file_obj in path.rglob("*"):
                # directories aren't real in s3/spaces, so we don't upload them
                if file_obj.is_dir():
                    continue

                # ensure a clean file path in the bucket
                if file_obj.is_absolute():
                    file_key = f"{file_obj.relative_to(abs_path)}"
                else:
                    file_key = f"{file_obj.absolute().relative_to(abs_path)}"
                spaces_key = f"{key_base}/{file_key}"
                package_files.append(PackageFile(local=file_obj, remote=self.bucket.Object(spaces_key)))
        else:
            raise ValueError(f"path must be a directory, received non-dir: {path}")

        for pfile in sorted(package_files, key=lambda x: f"{x.local}"):
            if files_match(pfile.local, pfile.remote):
                print(f"{pfile.local} already uploaded, skipping")
            else:
                print(f"Now uploading {pfile.local} to {pfile.remote.key}")
                self.client.upload_fileobj(
                    pfile.local.open("rb"), self.bucket.name, spaces_key, Callback=TransferProgress(pfile.local)
                )
                print()  # extra print to get past the \r in the TransferProgress callback

    def download_package(self, name, version):
        pass

    def check_package(self, name, version):
        pass


class TransferProgress(object):
    """Prints progress of a file transfer"""

    def __init__(self, file_obj):
        if type(file_obj) in (Path, PosixPath):
            self._filename = f"{file_obj.name}"
            self._size = file_obj.stat().st_size
        elif type(file_obj) is S3Object:
            self._filename = file_obj.key
            self._size = file_obj.content_length
        else:
            raise ValueError(
                f"file_obj type must be one of: {S3Object}, {Path}, {PosixPath}, but got: {type(file_obj)}"
            )
        self._seen_so_far = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        # To simplify, assume this is hooked up to a single filename
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            print(f"\r{self._filename}  {self._seen_so_far} / {self._size}  ({percentage:.2f}%)", end="", flush=True)
