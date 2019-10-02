from __future__ import print_function
import subprocess
import os


def unpack_folder(archive):
    print("Processing archive {}".format(archive))
    if not os.path.isfile(archive):
        print("Archive {} does not exist. Aborting.".format(archive))
        return

    target, ext = archive.split(".", 1)
    directory, archive_file = archive.rsplit("/", 1)

    if ext not in ["tar", "tar.gz"]:
        print("Not an archive ({}). Aborting.".format(archive))

    if os.path.isdir(target):
        print("Target directory {} exists. Assuming archive extracted.".format(target))
        return
    try:
        subprocess.check_call(
            "cd {}; tar --no-same-owner --no-same-permissions -xf {}".format(
                directory, archive_file
            ),
            shell=True,
        )
    except:
        subprocess.call("cd {}; rm -rf {}".format(directory, target), shell=True)
        raise


def unpack_file(archive):
    if not os.path.isfile(archive):
        print("Archive {} does not exist. Aborting.".format(archive))
        return

    directory, archive_file = archive.rsplit("/", 1)
    target, ext = archive_file.rsplit(".", 1)

    if ext != "gz":
        print("Not an archive ({}). Aborting.".format(archive))
        return

    target_path = os.path.join(directory, target)
    if os.path.isfile(target_path):
        print(
            "Target file exists ({}). Assuming archive extracted.".format(target_path)
        )
        return
    try:
        subprocess.check_call(
            "cd {}; zcat {} > {}".format(directory, archive_file, target), shell=True
        )
    except:
        subprocess.call("cd {}; rm -f {}".format(directory, target), shell=True)
        raise


if __name__ == "__main__":
    abspath = os.path.abspath(__file__)
    dname = os.path.dirname(abspath)
    os.chdir(dname)

    folders_to_extract = [
        "data/VEP/cache.tar",
        "data/seqrepo.tar",
        "thirdparty/vep.tar.gz",
        "thirdparty/bedtools2.tar.gz",
        "thirdparty/vcftools.tar.gz",
    ]

    files_to_extract = ["data/FASTA/human_g1k_v37_decoy.fasta.gz"]

    for archive in folders_to_extract:
        unpack_folder(archive)

    for archive in files_to_extract:
        unpack_file(archive)
