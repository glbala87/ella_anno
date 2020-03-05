import pytest
import os
import glob
import subprocess
import shutil
import tarfile

ANNO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
ANNO_DATA = os.environ["ANNO_DATA"]
DATASETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_datasets.json")
TAR_FILE = "/tmp/test_data.tar"


def iterate_testdata_files(relative=True):
    for folder, _, files in os.walk(ANNO_DATA):
        for file in files:
            assert os.path.isfile(os.path.join(folder, file))
            if relative:
                yield os.path.relpath(os.path.join(folder, file), ANNO_DATA)
            else:
                yield os.path.join(folder, file)


@pytest.fixture(autouse=True, scope="function")
def reset_testdata():
    print("Resetting testdata in {}".format(ANNO_DATA))
    empty_testdata()
    subprocess.call("python3 {}/ops/sync_data.py --generate -f {}".format(ANNO_ROOT, DATASETS), shell=True)
    os.remove(os.path.join(ANNO_DATA, "SYNC_DATA_LOG"))
    print("Data reset")


@pytest.fixture(autouse=True, scope="function")
def remove_tar():
    if os.path.isfile(TAR_FILE):
        os.remove(TAR_FILE)


def package_return_tar(PKG_NAMES=None):
    subprocess.call(
        "TAR_OUTPUT={} DATASETS={} {} /anno/ops/package_data".format(
            TAR_FILE, DATASETS, "PKG_NAMES={}".format(",".join(PKG_NAMES)) if PKG_NAMES else ""
        ),
        shell=True,
    )
    return tarfile.open(TAR_FILE, "r")


def empty_testdata():
    for path in glob.glob(os.path.join(ANNO_DATA, "*")):
        if os.path.isfile(path):
            os.remove(path)
        else:
            shutil.rmtree(path)


if __name__ == "__main__":
    iterate_testdata_files()
