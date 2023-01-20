#!/usr/bin/env python3

import argparse
import datetime
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from collections.abc import Mapping
from typing import Union
from util import hash_file, HashType


thirdparty_packages = {
    "htslib": {
        "url": "https://github.com/samtools/htslib",
        "version": "1.9",
        "sha256": "e04b877057e8b3b8425d957f057b42f0e8509173621d3eccaedd0da607d9929a",
        "filename": "htslib-{version}.tar.bz2",
        "url_prefix": "releases/download/{version}",
        "src_dir": "htslib-{version}",
        "installation": ["autoheader", "autoconf", "./configure", "make -j {max_procs}"],
    },
    "bedtools": {
        "url": "https://github.com/arq5x/bedtools2",
        "version": "2.29.0",
        "sha256": "a5140d265b774b628d8aa12bd952dd2331aa7c0ec895a460ee29afe2ce907f30",
        "filename": "bedtools-{version}.tar.gz",
        "src_dir": "bedtools2",
        "installation": ["sed -i 's/@python/@python3/g' Makefile", "make -j {max_procs}"],
    },
    "vcfanno": {
        "url": "https://github.com/brentp/vcfanno",
        "version": "0.3.2",
        "sha256": "a3e52b72d960edfc5754c4865f168b4ad228ceebbf87f15424792b3737f54f60",
        "filename": "vcfanno_linux64",
        "src_dir": "",  # binary only, no source needed
        "installation": ["chmod +x {filename}", "mv {filename} ../bin/vcfanno"],
    },
    "vcftools": {
        "url": "https://github.com/vcftools/vcftools",
        "version": "0.1.16",
        "sha256": "dbfc774383c106b85043daa2c42568816aa6a7b4e6abc965eeea6c47dde914e3",
        "filename": "vcftools-{version}.tar.gz",
        "src_dir": "vcftools-{version}",
        "installation": [
            "./configure",  # --prefix $(dirname $PWD)/vcftools",
            "make -j {max_procs}",
            "mkdir -p bin lib",
            "cp src/perl/*.pm lib/",
            "cp src/perl/vcf-* bin/",
            "cp src/cpp/vcftools bin/",
        ],
    },
    "vep": {
        "url": "https://github.com/Ensembl/ensembl-vep",
        "version": "108.2",
        "sha256": "73184667649e3867518c855aedd406880afe1e06d70599d5c03f70543da662d3",
        "url_prefix": "archive/release",
        "filename": "{version}.tar.gz",
        "src_dir": "ensembl-vep-release-{version}",
        "installation": ["perl INSTALL.pl -n -a a -s homo_sapiens_merged -y GRCh37"],
    },
    "vt": {
        "url": "https://github.com/atks/vt",
        "version": "0.57721",
        "sha256": "8f06d464ec5458539cfa30f81a034f47fe7f801146fe8ca80c14a3816b704e17",
        "url_prefix": "archive",
        "filename": "{version}.tar.gz",
        "src_dir": "vt-{version}",
        "installation": ["make -j {max_procs}"],
    },
}
TOUCHFILE = "SETUP_COMPLETE"
MAX_PROCS = len(os.sched_getaffinity(0))
this_dir = Path(__file__).parent.absolute()
anno_root = this_dir.parent
default_dir = anno_root / "thirdparty"
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory",
        "-d",
        default=default_dir,
        help="directory to extract the thirdparty packages into. Default: {}".format(default_dir),
    )
    parser.add_argument(
        "--package",
        "-p",
        metavar="PACKAGE_NAME",
        choices=sorted(thirdparty_packages.keys()),
        help=f"install one of: {', '.join(sorted(thirdparty_packages.keys()))}",
    )
    parser.add_argument(
        "--max-processes",
        "-x",
        type=int,
        default=MAX_PROCS,
        help="maximum number of processes to run in parallel",
    )
    parser.add_argument("--clean", action="store_true", help="clean up intermediate files")
    parser.add_argument("--verbose", action="store_true", help="be extra chatty")
    parser.add_argument("--debug", action="store_true", help="run in debug mode")
    args = parser.parse_args()

    if args.debug:
        setattr(args, "verbose", True)
        logger.setLevel(logging.DEBUG)

    # make sure thirdparty dir exists
    args.directory.mkdir(parents=True, exist_ok=True)

    if args.package and args.package in thirdparty_packages.keys():
        install_packages = {args.package: thirdparty_packages[args.package]}
    else:
        install_packages = thirdparty_packages

    for pkg_name, pkg in install_packages.items():
        # add args.max_processes to pkg so we can use a single dict with .format statements
        pkg["max_procs"] = args.max_processes
        if pkg["src_dir"] == "":
            pkg_dir = args.directory
            final_dir = pkg_dir
        elif "{version}" in pkg["src_dir"]:
            pkg_dir = args.directory / Path(pkg["src_dir"].format(**pkg))
            final_dir = args.directory / Path(pkg["src_dir"].replace("-{version}", ""))
        else:
            pkg_dir = args.directory / Path(pkg["src_dir"])
            final_dir = pkg_dir

        if args.verbose:
            logger.info(f"Using pkg_dir: {pkg_dir}")
            logger.info(f"Using final_dir: {final_dir}\n")

        pkg_touchfile = final_dir / TOUCHFILE
        # if src_dir is an empty string, a binary is downloaded and moved to anno_root/bin, so nothing to delete
        if pkg["src_dir"] != "":
            if final_dir.exists():
                logger.debug(f"Found existing final_dir: {final_dir}")
                if pkg_touchfile.exists():
                    logger.info(
                        f"Package {pkg_name} already installed on {pkg_touchfile.read_text()}, skipping"
                    )
                    continue
                else:
                    # assume failed install because no TOUCHFILE
                    shutil.rmtree(final_dir)
            elif pkg_dir.exists():
                # pkg_dir exists, but final_dir does not assume failed installation and remove
                shutil.rmtree(pkg_dir)

        if args.verbose:
            logger.info(f"Fetching {pkg_name}...\n")
        pkg_artifact = github_fetch_package(pkg, args.directory)

        if is_archive(pkg_artifact):
            if args.verbose:
                logger.info(f"Compiling / packaging {pkg_name}")
            subprocess.run(["tar", "xvf", pkg_artifact], cwd=args.directory, check=True)
        else:
            if args.verbose:
                logger.info(f"Not extracting non-archive artifact {pkg_artifact}")

        if args.clean and is_archive(pkg_artifact):
            pkg_artifact.unlink()

        compile_dir = args.directory / pkg_dir
        for step_num, step in enumerate(pkg["installation"]):
            step_str = step.format(**pkg)
            logger.debug(f"DEBUG - Step {step_num}: {step}\n")
            step_resp = subprocess.run(step_str, shell=True, cwd=compile_dir)
            if step_resp.returncode != 0:
                raise Exception(f"Error installing package {pkg_name} on step: {step_str}")

        # the packaged src_dir sometimes includes the current version number
        # we don't want that in the path, so rename it to non-versioned
        if final_dir != pkg_dir:
            pkg_dir.rename(final_dir)

        # create a touchfile to mark that setup was successful, if src_dir available to write to
        if pkg["src_dir"]:
            pkg_touchfile.write_text(f"{datetime.datetime.utcnow()}")

        if args.debug:
            break


def github_fetch_package(pkg: Mapping, dest: Path, hash="sha256") -> Path:
    """downloads a release archive from github"""
    hash_type = HashType[hash]
    release_file = pkg["filename"].format(**pkg)
    release_filepath = dest / release_file
    if release_filepath.is_file():
        this_hash = hash_file(release_filepath, hash_type=hash_type)
        if this_hash == pkg[hash]:
            logger.info("Re-using existing package")
            return release_filepath
        else:
            logger.info("Removing partially downloaded package")
            release_filepath.unlink()

    default_url_prefix = (
        pkg["url_prefix"] if pkg.get("url_prefix") else "releases/download/v{version}"
    )
    release_url = f"{pkg['url']}/{default_url_prefix}".format(**pkg)
    full_url = f"{release_url}/{release_file}"

    subprocess.run(["wget", full_url], cwd=dest, check=True)
    this_hash = hash_file(release_filepath, hash_type=hash_type)
    if this_hash != pkg[hash]:
        raise Exception(
            f"Checksum mismatch on {release_file}. Expected {pkg[hash]}, but got {this_hash}"
        )

    return release_filepath


def is_archive(filename: Union[str, Path]):
    return bool(re.search(r"\.tar\.(?:gz|bz2)$", f"{filename}"))


###


if __name__ == "__main__":
    main()
