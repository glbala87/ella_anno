from __future__ import print_function

from collections import OrderedDict
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import toml
from conftest import (
    iterate_testdata_files,
    empty_testdata,
    package_return_tar,
    ANNO_DATA,
    DATASETS,
    TAR_FILE,
    SOURCES_JSON,
    VCFANNO,
)


def data_md5sum():
    md5sums = {}
    for file in iterate_testdata_files(relative=False):
        hash = hashlib.md5()
        with open(file, "rb") as f:
            hash.update(f.read())

        md5sums[os.path.relpath(file, ANNO_DATA)] = hash.hexdigest()
    return md5sums


def data_empty():
    return list(iterate_testdata_files()) == []


def unpack_data(raise_on_error=True):
    try:
        return subprocess.check_output(
            "DATASETS_FILE={} TAR_INPUT={} /anno/ops/unpack_data".format(DATASETS, TAR_FILE),
            shell=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as e:
        if not raise_on_error:
            return e.output.decode("utf-8")
        else:
            print(e.output.decode("utf-8"), file=sys.stderr)
            raise


def data_vcfanno():
    if VCFANNO.exists():
        toml_data = toml.load(VCFANNO, _dict=OrderedDict)
        if "annotation" in toml_data:
            return toml_data["annotation"]
    return []


def string_to_tar(tar_file, name, string):
    s = io.BytesIO(string.encode("utf-8"))
    info = tarfile.TarInfo(name=name)
    info.size = len(string)
    tar_file.addfile(tarinfo=info, fileobj=s)
    dirname = os.path.dirname(name)
    if dirname and dirname not in tar_file.getnames():
        dir_info = tarfile.TarInfo(name=dirname)
        dir_info.type = tarfile.DIRTYPE
        tar_file.addfile(dir_info)


def test_empty_data():
    "Try to unpack data on an empty folder"
    md5_before = data_md5sum()
    package_return_tar()
    empty_testdata()
    assert data_empty(), "Data folder is not empty"

    unpack_data()
    assert not data_empty(), "Data folder is empty after extracting"
    md5_after = data_md5sum()
    md5_after.pop("UNPACK_DATA_LOG")
    assert md5_before == md5_after


def test_same_data():
    "Try to unpack data that is equal to data already present"
    assert not data_empty()
    md5_before = data_md5sum()

    package_return_tar()
    unpack_data()

    md5_after = data_md5sum()
    md5_after.pop("UNPACK_DATA_LOG")

    assert md5_before == md5_after

    pass


def test_new_version():
    "Try to unpack data with an updated version"
    # data_tar = package_return_tar(PKG_NAMES=["dataset1"])

    files_before = set(iterate_testdata_files())

    updated_tar_file = tarfile.open(TAR_FILE, mode="w")

    sources_json = json.load(open(SOURCES_JSON))
    sources_json["dataset1"]["timestamp"] = "2020-01-01 00:00:00.000000"
    sources_json["dataset1"]["version"] = 2
    sources_json["dataset1"]["vcfanno"][0]["names"] = ["SOME_FIELD_VERSION2_TRANSLATED"]
    string_to_tar(updated_tar_file, SOURCES_JSON.name, json.dumps(sources_json, indent=2))
    string_to_tar(updated_tar_file, "DATASET1/dataset1.vcf", "SOME TESTDATA FOR VERSION 2 OF DATASET1\n")
    string_to_tar(updated_tar_file, "DATASET1/DATA_READY", "timestamp: 2020-01-01 00:00:00.000000\nversion: '2'")
    string_to_tar(updated_tar_file, "DATASET1/MD5SUM", "dabla")
    string_to_tar(updated_tar_file, "PACKAGES", "dataset1\n")
    updated_tar_file.close()

    unpack_data()

    files_after = set(iterate_testdata_files())
    files_after.remove("UNPACK_DATA_LOG")
    assert files_before == files_after

    data_sources_json = json.load(SOURCES_JSON.open())
    assert data_sources_json == sources_json
    assert (
        open(os.path.join(ANNO_DATA, "DATASET1/dataset1.vcf"), "r").read()
        == "SOME TESTDATA FOR VERSION 2 OF DATASET1\n"
    )

    assert (
        open(os.path.join(ANNO_DATA, "DATASET1/DATA_READY"), "r").read()
        == "timestamp: 2020-01-01 00:00:00.000000\nversion: '2'"
    )


def test_new_package():
    "Try to unpack data with a new package"
    files_before = set(iterate_testdata_files())
    new_package_tar_file = tarfile.open(TAR_FILE, mode="w")

    original_sources_json = json.load(SOURCES_JSON.open())
    packaged_sources_json = json.load(SOURCES_JSON.open())

    packaged_sources_json["dataset1"]["version"] = "SOME NEW VERSION THAT SHOULD NOT BE ADDED BACK"
    packaged_sources_json["dataset2"]["version"] = "SOME NEW VERSION THAT SHOULD NOT BE ADDED BACK"
    packaged_sources_json["dataset3"]["version"] = "SOME NEW VERSION THAT SHOULD NOT BE ADDED BACK"
    packaged_sources_json["dataset4"] = {
        "description": "Test dataset 4",
        "version": "20200101",
        "timestamp": "2020-01-01 00:00:00.000000",
        "vcfanno": [
            {
                "file": "DATASET4/dataset4.vcf",
                "fields": ["SOME_FIELD_DATASET4"],
                "names": ["SOME_FIELD_DATASET4_TRANSLATED"],
                "ops": ["first"],
            }
        ],
    }

    assert original_sources_json != packaged_sources_json
    string_to_tar(new_package_tar_file, SOURCES_JSON.name, json.dumps(packaged_sources_json, indent=2))
    string_to_tar(new_package_tar_file, "DATASET4/dataset4.vcf", "SOME TESTDATA FOR DATASET4\n")
    string_to_tar(
        new_package_tar_file, "DATASET4/DATA_READY", "timestamp: 2020-01-01 00:00:00.000000\nversion: '20200101'",
    )
    string_to_tar(new_package_tar_file, "DATASET4/MD5SUM", "dabla")
    string_to_tar(new_package_tar_file, "PACKAGES", "dataset4\n")
    new_package_tar_file.close()

    unpack_data()

    files_after = set(iterate_testdata_files())
    files_after.remove("UNPACK_DATA_LOG")
    assert files_before - files_after == set()  # No files removed
    assert files_after - files_before == set(["DATASET4/MD5SUM", "DATASET4/DATA_READY", "DATASET4/dataset4.vcf"])

    # Check that sources are correctly updated
    sources_json = json.load(SOURCES_JSON.open())
    assert set(sources_json.keys()) == set(packaged_sources_json.keys())
    assert sources_json["dataset1"] == original_sources_json["dataset1"]
    assert sources_json["dataset2"] == original_sources_json["dataset2"]
    assert sources_json["dataset3"] == original_sources_json["dataset3"]
    assert sources_json["dataset4"] == packaged_sources_json["dataset4"]


def test_new_filename():
    "try to unpack an existing package with a new filename"
    new_package_tar_file = tarfile.open(TAR_FILE, mode="w")
    orig_vcfanno = data_vcfanno()
    orig_vcfanno_files = [x["file"] for x in orig_vcfanno]

    original_sources_json = json.load(SOURCES_JSON.open())
    packaged_sources_json = json.load(SOURCES_JSON.open())

    new_version = "v2.0"
    # re-generate the sources.json output manually since we don't want to re-run `sync_data.py --generate`
    datasets_json = json.load(DATASETS.open())
    format_opts = {
        "destination": datasets_json["dataset3"]["destination"],
        "version": new_version,
    }
    packaged_sources_json["dataset3"]["version"] = new_version
    filename = datasets_json["dataset3"]["vcfanno"][0]["file"].format(**format_opts)
    packaged_sources_json["dataset3"]["vcfanno"][0]["file"] = filename

    assert original_sources_json != packaged_sources_json
    string_to_tar(new_package_tar_file, SOURCES_JSON.name, json.dumps(packaged_sources_json, indent=2))
    string_to_tar(new_package_tar_file, filename, "NEW TESTDATA FOR DATASET3\n")
    string_to_tar(
        new_package_tar_file,
        "DATASET3/DATA_READY",
        "timestamp: 2020-06-06 00:00:00.000000\nversion: '{}'".format(new_version),
    )
    string_to_tar(new_package_tar_file, "DATASET3/MD5SUM", "dabla")
    string_to_tar(new_package_tar_file, "PACKAGES", "dataset3\n")
    new_package_tar_file.close()

    unpack_log = unpack_data()

    new_vcfanno = data_vcfanno()
    new_vcfanno_files = [x["file"] for x in new_vcfanno]

    assert len(orig_vcfanno) == len(new_vcfanno)
    assert [x["file"] for x in orig_vcfanno] != [x["file"] for x in new_vcfanno]
    assert (
        packaged_sources_json["dataset3"]["vcfanno"][0]["file"] in new_vcfanno_files
        and packaged_sources_json["dataset3"]["vcfanno"][0]["file"] not in orig_vcfanno_files
    )
    assert (
        original_sources_json["dataset3"]["vcfanno"][0]["file"] in orig_vcfanno_files
        and original_sources_json["dataset3"]["vcfanno"][0]["file"] not in new_vcfanno_files
    )


def test_cleanup():
    "Try to abort unpack to revert changes"
    files_before = set(iterate_testdata_files())
    md5sum_before = data_md5sum()

    # Create a tar file with missing PACKAGES-file
    updated_tar_file = tarfile.open(TAR_FILE, mode="w")
    sources_json = json.load(SOURCES_JSON.open())
    sources_json["dataset1"]["timestamp"] = "2020-01-01 00:00:00.000000"
    sources_json["dataset1"]["version"] = 2
    sources_json["dataset1"]["vcfanno"][0]["names"] = ["SOME_FIELD_VERSION2_TRANSLATED"]
    string_to_tar(updated_tar_file, SOURCES_JSON.name, json.dumps(sources_json, indent=2))

    string_to_tar(updated_tar_file, "DATASET1/dataset1.vcf", "SOME TESTDATA FOR VERSION 2 OF DATASET1\n")

    string_to_tar(updated_tar_file, "DATASET1/DATA_READY", "timestamp: 2020-01-01 00:00:00.000000\nversion: '2'")

    updated_tar_file.close()

    log = unpack_data(raise_on_error=False)
    assert "Moving files in folders affected to temporary backup folder" in log  # Files have been moved
    assert "Something went wrong with unpacking data. Reverting changes." in log  # Process failed
    assert "Changes reverted." in log

    files_after = set(iterate_testdata_files())
    assert files_before == files_after

    md5sum_after = data_md5sum()

    # Data is equal
    assert md5sum_before == md5sum_after
