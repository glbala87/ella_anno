from __future__ import print_function

import hashlib
import io
import json
import os
import subprocess
from StringIO import StringIO
import tarfile
from conftest import iterate_testdata_files, empty_testdata, package_return_tar, TAR_FILE, ANNO_DATA


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
            "TAR_INPUT={} /anno/ops/unpack_data".format(TAR_FILE), shell=True, stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as e:
        if not raise_on_error:
            return e.output
        else:
            raise


def file_length(filename):
    num_lines = 0
    with io.open(filename) as f:
        for line in f:
            num_lines += 1
    return num_lines


def string_to_tar(tar_file, name, string):
    s = StringIO(string)
    info = tarfile.TarInfo(name=name)
    info.size = len(s.buf)
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

    updated_tar_file = tarfile.TarFile(TAR_FILE, mode="w")

    sources_json = json.load(open(os.path.join(ANNO_DATA, "sources.json")))
    sources_json["dataset1"]["timestamp"] = "2020-01-01 00:00:00.000000"
    sources_json["dataset1"]["version"] = 2
    sources_json["dataset1"]["vcfanno"][0]["names"] = ["SOME_FIELD_VERSION2_TRANSLATED"]
    string_to_tar(updated_tar_file, "sources.json", json.dumps(sources_json, indent=2))
    string_to_tar(updated_tar_file, "DATASET1/dataset1.vcf", "SOME TESTDATA FOR VERSION 2 OF DATASET1\n")
    string_to_tar(updated_tar_file, "DATASET1/DATA_READY", "timestamp: 2020-01-01 00:00:00.000000\nversion: '2'")
    string_to_tar(updated_tar_file, "DATASET1/MD5SUM", "dabla")
    string_to_tar(updated_tar_file, "PACKAGES", "dataset1\n")
    updated_tar_file.close()

    unpack_data()

    files_after = set(iterate_testdata_files())
    files_after.remove("UNPACK_DATA_LOG")
    assert files_before == files_after

    data_sources_json = json.load(open(os.path.join(ANNO_DATA, "sources.json")))
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
    new_package_tar_file = tarfile.TarFile(TAR_FILE, mode="w")

    original_sources_json = json.load(open(os.path.join(ANNO_DATA, "sources.json")))
    packaged_sources_json = json.load(open(os.path.join(ANNO_DATA, "sources.json")))

    packaged_sources_json["dataset1"]["version"] = "2"
    packaged_sources_json["dataset2"]["version"] = "SOME NEW VERSION THAT SHOULD NOT BE ADDED BACK"
    packaged_sources_json["dataset3"] = {
        "description": "Test dataset 3",
        "version": "20200101",
        "timestamp": "2020-01-01 00:00:00.000000",
        "vcfanno": [
            {
                "file": "/anno/test_data/datasets/DATASET3/dataset3.vcf",
                "fields": ["SOME_FIELD_DATASET3"],
                "names": ["SOME_FIELD_DATASET3_TRANSLATED"],
                "ops": ["first"],
            }
        ],
    }

    assert original_sources_json != packaged_sources_json
    string_to_tar(new_package_tar_file, "sources.json", json.dumps(packaged_sources_json, indent=2))
    string_to_tar(new_package_tar_file, "datasets/DATASET3/dataset3.vcf", "SOME TESTDATA FOR DATASET3\n")
    string_to_tar(
        new_package_tar_file,
        "datasets/DATASET3/DATA_READY",
        "timestamp: 2020-01-01 00:00:00.000000\nversion: '20200101'",
    )
    string_to_tar(new_package_tar_file, "datasets/DATASET3/MD5SUM", "dabla")
    string_to_tar(new_package_tar_file, "PACKAGES", "dataset3\n")
    new_package_tar_file.close()

    unpack_data()

    files_after = set(iterate_testdata_files())
    files_after.remove("UNPACK_DATA_LOG")
    assert files_before - files_after == set()  # No files removed
    assert files_after - files_before == set(
        ["datasets/DATASET3/MD5SUM", "datasets/DATASET3/DATA_READY", "datasets/DATASET3/dataset3.vcf"]
    )

    # Check that sources are correctly updated
    sources_json = json.load(open(os.path.join(ANNO_DATA, "sources.json")))
    assert set(sources_json.keys()) == set(packaged_sources_json.keys())
    assert sources_json["dataset1"] == original_sources_json["dataset1"]
    assert sources_json["dataset2"] == original_sources_json["dataset2"]
    assert sources_json["dataset3"] == packaged_sources_json["dataset3"]


def test_new_filename():
    "try to unpack an existing package with a new filename"
    new_package_tar_file = tarfile.TarFile(TAR_FILE, mode="w")
    orig_vcfanno_len = file_length(os.path.join(ANNO_DATA, "vcfanno_config.toml"))

    original_sources_json = json.load(open(os.path.join(ANNO_DATA, "sources.json")))
    packaged_sources_json = json.load(open(os.path.join(ANNO_DATA, "sources.json")))

    new_version = "2"
    new_filename = "DATASET1/dataset1_v2.vcf"
    orig_filename = original_sources_json["dataset1"]["vcfanno"][0]["file"]
    packaged_sources_json["dataset1"]["version"] = new_version
    packaged_sources_json["dataset1"]["vcfanno"][0]["file"] = new_filename

    assert original_sources_json != packaged_sources_json
    string_to_tar(new_package_tar_file, "sources.json", json.dumps(packaged_sources_json, indent=2))
    string_to_tar(new_package_tar_file, "datasets/{}".format(new_filename), "NEW TESTDATA FOR DATASET1\n")
    string_to_tar(
        new_package_tar_file,
        "datasets/{}".format(new_filename),
        "timestamp: 2020-01-01 00:00:00.000000\nversion: '20200101'",
    )
    string_to_tar(new_package_tar_file, "datasets/DATASET1/MD5SUM", "dabla")
    string_to_tar(new_package_tar_file, "PACKAGES", "dataset1\n")
    new_package_tar_file.close()

    unpack_data()

    new_vcfanno_len = file_length(os.path.join(ANNO_DATA, "vcfanno_config.toml"))
    assert orig_vcfanno_len == new_vcfanno_len


def test_cleanup():
    "Try to abort unpack to revert changes"
    files_before = set(iterate_testdata_files())
    md5sum_before = data_md5sum()

    # Create a tar file with missing PACKAGES-file
    updated_tar_file = tarfile.TarFile(TAR_FILE, mode="w")
    sources_json = json.load(open(os.path.join(ANNO_DATA, "sources.json")))
    sources_json["dataset1"]["timestamp"] = "2020-01-01 00:00:00.000000"
    sources_json["dataset1"]["version"] = 2
    sources_json["dataset1"]["vcfanno"][0]["names"] = ["SOME_FIELD_VERSION2_TRANSLATED"]
    string_to_tar(updated_tar_file, "sources.json", json.dumps(sources_json, indent=2))

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
