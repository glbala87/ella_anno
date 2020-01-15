import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from botocore.handlers import disable_signing
import csv
from collections import namedtuple
from functools import partial
import logging
import multiprocessing
from multiprocessing.pool import ThreadPool
import os
from pathlib import Path, PosixPath
import subprocess
import sys

import pdb


SPACES_REGION = "fra1"
SPACES_ENDPOINT = f"https://{SPACES_REGION}.digitaloceanspaces.com"
SPACES_BUCKET = "ella-anno"
ROOT_DIR = Path(__file__).absolute().parent.parent
DATA_DIR = ROOT_DIR / "data"
# boto3 doesn't let you directly import classes, so we have to do a hacky string "class" for checking type
S3Object = "<class 'boto3.resources.factory.s3.Object'>"
PackageFile = namedtuple("PackageFile", ["local", "remote"])
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
max_pool_conns = 10 * os.cpu_count()
client_config = BotoConfig(max_pool_connections=max_pool_conns)


def s3_object_exists(s3_object):
    try:
        s3_object.load()
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise e
    return True


def files_match(package_file):
    return (
        package_file.local.exists()
        and s3_object_exists(package_file.remote)
        and package_file.local.stat().st_size == package_file.remote.content_length
    )


class DataManager(object):
    _bucket = None
    _client = None
    _s3 = None
    _session = None
    _pool = None
    _max_threads = None
    _show_progress = False

    def __init__(self, access_key=None, access_secret=None, **kwargs):
        self.access_key = os.environ.get("SPACES_KEY", access_key)
        self.access_secret = os.environ.get("SPACES_SECRET", access_secret)
        self.region = kwargs.get("region_name", SPACES_REGION)
        self.endpoint = kwargs.get("endpoint_url", SPACES_ENDPOINT)

        for key, val in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, val)
            else:
                logger.warning(f"can't set unexpected kwarg in DataManager: {key}={val}")

    @property
    def pool(self):
        if self._pool is None:
            self._pool = ThreadPool(processes=self._max_threads)

        return self._pool

    @property
    def client(self):
        if self._client is None:
            self._client = self.session.client("s3", endpoint_url=self.endpoint, config=client_config)

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
                self._s3 = boto3.resource(
                    "s3", region_name=self.region, endpoint_url=self.endpoint, config=client_config
                )
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

    def upload_package(self, name, version, path, show_progress=False):
        abs_path = path.absolute()
        key_base = f"{path}/{version}"
        upload_func = partial(self._upload_file, show_progress=show_progress)

        # get a list of keys already in the bucket for this package version
        # checking for a key in the array is faster than running s3_object_exists for every file on new package uploads
        remote_keys = set([o.key for o in self.bucket.objects.filter(Prefix=key_base)])
        skip_count = 0
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
                package_file = PackageFile(local=file_obj, remote=self.bucket.Object(spaces_key))
                if package_file.remote.key in remote_keys and files_match(package_file):
                    skip_count += 1
                else:
                    package_files.append(package_file)
        else:
            raise ValueError(f"path must be a directory, received non-dir: {path}")

        if skip_count > 0:
            logger.info(f"Skipped {skip_count} files that had already been uploaded")

        if package_files:
            logger.info(f"Uploading {len(package_files)} files for {name}")
            self.pool.map(
                upload_func, sorted([p for p in package_files if not files_match(p)], key=lambda x: f"{x.local}")
            )
        logger.info(f"Finished processing all files for {name}")

    def download_package(self, name, version, path, show_progress=False):
        abs_path = path.absolute()
        key_base = f"{path}/{version}"
        download_func = partial(self._download_file, show_progress=show_progress)

        # check that the package version exists in the bucket and bail if not
        data_ready = self.bucket.Object(f"{key_base}/DATA_READY")
        if not s3_object_exists(data_ready):
            raise Exception(
                f"Data for {name} version {version} incomplete or non-existent. Check requested/available versions."
            )

        skip_count = 0
        package_files = list()
        for obj in self.bucket.objects.filter(Prefix=key_base):
            package_file = PackageFile(
                local=Path(obj.key.replace(f"/{version}/", "/")), remote=self.bucket.Object(obj.key)
            )
            if files_match(package_file):
                skip_count += 1
            else:
                package_files.append(package_file)

        if skip_count > 0:
            logger.info(f"Skipping {skip_count} files already downloaded")

        if package_files:
            logger.info(f"Downloading {len(package_files)} files for {name} to {abs_path}")
            self.pool.map(download_func, sorted(package_files))
        logger.info(f"Finished downloading all files for {name}")

    def _upload_file(self, package_file, show_progress=False):
        logging.debug(f"Uploading {package_file.local.name} to {package_file.remote.key}")
        cb = TransferProgress(package_file.local) if self._show_progress else None
        self.client.upload_fileobj(
            package_file.local.open("rb"), self.bucket.name, package_file.remote.key, Callback=cb
        )
        if cb:
            print()  # extra print to get past the \r in the TransferProgress callback

    def _download_file(self, package_file, show_progress=False):
        logging.debug(f"Downloading {package_file.remote.key} to {package_file.local}")
        cb = TransferProgress(package_file.remote) if self._show_progress else None
        package_file.local.parent.mkdir(parents=True, exist_ok=True)
        package_file.remote.download_fileobj(package_file.local.open("wb"), Callback=cb)
        if cb:
            print()  # extra print to get past the \r in the TransferProgress callback


class TransferProgress(object):
    """Prints progress of a file transfer"""

    def __init__(self, file_obj):
        if type(file_obj) in (Path, PosixPath):
            self._filename = f"{file_obj.name}"
            self._size = file_obj.stat().st_size
        # hacky workaround because boto3 is too cool for importable classes
        elif str(type(file_obj)) == S3Object:
            self._filename = file_obj.key
            self._size = file_obj.content_length
        else:
            raise ValueError(
                f"file_obj type must be one of: {S3Object}, {Path}, {PosixPath}, but got: {type(file_obj)}"
            )
        self._seen_so_far = 0
        self._lock = multiprocessing.Lock()

    def __call__(self, bytes_amount):
        # To simplify, assume this is hooked up to a single filename
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            print(
                f"\r{self._filename}  {self._seen_so_far} / {self._size}  ({percentage:.2f}%)",
                end="",
                flush=True,
                file=sys.stdout,
            )
