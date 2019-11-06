#!/usr/bin/env python3

import os
from pathlib import Path
import subprocess


def unpack_folder(archive):
    print("Processing archive {}".format(archive))
    if not archive.exists():
        print("Archive {} does not exist. Aborting.".format(archive))
        return

    target, ext = str(archive).split(".", 1)
    directory = archive.parent
    archive_file = archive.name

    if ext not in ["tar", "tar.gz"]:
        print("Not an archive ({}). Aborting.".format(archive))

    if Path(target).is_dir():
        print("Target directory {} exists. Assuming archive extracted.".format(target))
        return
    try:
        subprocess.check_call(
            "tar --no-same-owner --no-same-permissions -xf {}".format(archive_file), cwd=directory, shell=True
        )
    except:
        subprocess.call("rm -rf {}".format(target), cwd=directory, shell=True)
        raise


def unpack_file(archive):
    if not archive.is_file():
        print("Archive {} does not exist. Aborting.".format(archive))
        return

    target, ext = str(archive).split(".", 1)
    directory = archive.parent
    archive_file = archive.name

    if ext != "gz":
        print("Not an archive ({}). Aborting.".format(archive))
        return

    target_path = directory / target
    if target_path.is_file():
        print("Target file exists ({}). Assuming archive extracted.".format(target_path))
        return
    try:
        subprocess.check_call("zcat {} > {}".format(archive_file, target), cwd=directory, shell=True)
    except:
        subprocess.call("rm -f {}".format(target), cwd=directory, shell=True)
        raise


if __name__ == "__main__":
    abspath = Path(__file__).absolute()
    dname = abspath.parent
    os.chdir(dname)

    folders_to_extract = [Path("data.tar").absolute(), Path("thirdparty.tar.gz").absolute()]
    files_to_extract = [Path("data/FASTA/human_g1k_v37_decoy.fasta.gz").absolute()]

    for archive in folders_to_extract:
        unpack_folder(archive)

    for archive in files_to_extract:
        unpack_file(archive)
