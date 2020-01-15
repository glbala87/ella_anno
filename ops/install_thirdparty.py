#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
from util import hash_file


thirdparty_packages = {
    "htslib": {
        "url": "https://github.com/samtools/htslib",
        "version": "1.9",
        "sha256": "e04b877057e8b3b8425d957f057b42f0e8509173621d3eccaedd0da607d9929a",
        "filename": "htslib-{version}.tar.bz2",
        "url_prefix": "releases/download/{version}",
        "src_dir": "htslib-{version}",
        "installation": ["autoheader", "autoconf", "./configure", "make"],
    },
    "bedtools": {
        "url": "https://github.com/arq5x/bedtools2",
        "version": "2.29.0",
        "sha256": "a5140d265b774b628d8aa12bd952dd2331aa7c0ec895a460ee29afe2ce907f30",
        "filename": "bedtools-{version}.tar.gz",
        "src_dir": "bedtools2",
        "installation": ["make"],
    },
    # "vcfanno": {
    #     "url": "https://github.com/brentp/vcfanno",
    #     "version": "0.2.8",
    #     "sha256": "",
    #     "download": {"filename": ""},
    # },
    "vcftools": {
        "url": "https://github.com/vcftools/vcftools",
        "version": "0.1.16",
        "sha256": "dbfc774383c106b85043daa2c42568816aa6a7b4e6abc965eeea6c47dde914e3",
        "filename": "vcftools-{version}.tar.gz",
        "src_dir": "vcftools-{version}",
        "installation": [
            "./configure",  # --prefix $(dirname $PWD)/vcftools",
            "make",
            "mkdir -p bin lib",
            "cp src/perl/*.pm lib/",
            "cp src/perl/vcf-* bin/",
            "cp src/cpp/vcftools bin/",
        ],
    },
    "vep": {
        "url": "https://github.com/Ensembl/ensembl-vep",
        "version": "98.3",
        "url_prefix": "archive/release",
        "filename": "{version}.tar.gz",
        "src_dir": "ensembl-vep-release-{version}",
        "sha256": "ef878d61071c37d35f00909c21cd7769175eb91b331e985413435dfab2474bd7",
        "installation": ["perl INSTALL.pl -a a -s homo_sapiens_merged -y GRCh37"],
    },
    "vt": {
        "url": "https://github.com/atks/vt",
        "version": "0.57721",
        "sha256": "",
        "url_prefix": "archive",
        "filename": "{version}.tar.gz",
        "src_dir": "vt-{version}",
        "sha256": "8f06d464ec5458539cfa30f81a034f47fe7f801146fe8ca80c14a3816b704e17",
        "installation": ["make -j {max_procs}"],
    },
}
TOUCHFILE = "SETUP_COMPLETE"
this_dir = Path(__file__).parent.absolute()
anno_root = this_dir.parent
default_dir = anno_root / "thirdparty"
args = None
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    global args

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
        choices=thirdparty_packages.keys(),
        help=f"install one of: {', '.join(sorted(thirdparty_packages.keys()))}",
    )
    parser.add_argument(
        "--max-processes", "-x", type=int, default=os.cpu_count(), help="maximum number of processes to run in parallel"
    )
    parser.add_argument("--clean", action="store_true", help="clean up intermediate files")
    parser.add_argument("--verbose", action="store_true", help="be extra chatty")
    parser.add_argument("--debug", action="store_true", help="run in debug mode")
    args = parser.parse_args()

    if args.debug:
        setattr(args, "verbose", True)
        logger.setLevel(logging.DEBUG)

    if not os.path.exists(args.directory):
        os.makedirs(args.directory)

    if args.package and args.package in thirdparty_packages.keys():
        install_packages = {args.package: thirdparty_packages[args.package]}
    else:
        install_packages = thirdparty_packages

    for pkg_name, pkg in install_packages.items():
        format_opts = {"version": pkg["version"], "max_procs": args.max_processes}
        pkg_artifact = pkg["filename"].format(**format_opts)
        if "{version}" in pkg["src_dir"]:
            pkg_dir = args.directory / Path(pkg["src_dir"].format(**format_opts))
            final_dir = args.directory / Path(pkg["src_dir"].replace("-{version}", ""))
        else:
            pkg_dir = args.directory / Path(pkg["src_dir"])
            final_dir = pkg_dir

        if args.verbose:
            logger.info(f"Using pkg_dir: {pkg_dir}", file=sys.stderr)
            logger.info(f"Using final_dir: {final_dir}\n", file=sys.stderr)

        pkg_touchfile = final_dir / TOUCHFILE
        if final_dir.exists():
            logger.debug(f"Found existing final_dir: {final_dir}")
            if pkg_touchfile.exists():
                logger.info(f"Package {pkg_name} already installed on {pkg_touchfile.read_text()}, skipping")
                continue
            else:
                # assume failed install because no TOUCHFILE
                shutil.rmtree(final_dir)
        elif pkg_dir.exists():
            # pkg_dir exists, but final_dir does not assume failed installation and remove
            shutil.rmtree(pkg_dir)

        if args.verbose:
            logger.info(f"Fetching {pkg_name}...\n")
        github_fetch_package(pkg, args.directory, format_opts)

        if args.verbose:
            logger.info(f"Compiling / packaging {pkg_name}")
        subprocess.run(["tar", "xvf", pkg_artifact], cwd=args.directory, check=True)

        if args.clean:
            os.remove(os.path.join(args.directory, pkg_artifact))

        compile_dir = args.directory / pkg_dir
        for step_num, step in enumerate(pkg["installation"]):
            step_str = step.format(**format_opts)
            logger.debug(f"DEBUG - Step {step_num}: {step}\n")
            step_resp = subprocess.run(step_str, shell=True, cwd=compile_dir)
            if step_resp.returncode != 0:
                raise Exception(f"Error installing package {pkg_name} on step: {step}")

        # the packaged src_dir sometimes includes the current version number
        # we don't want that in the path, so rename it to non-versioned
        if final_dir != pkg_dir:
            pkg_dir.rename(final_dir)

        # create a touchfile to mark that setup was successful
        pkg_touchfile.write_text(f"{datetime.datetime.utcnow()}")

        if args.debug:
            break


def github_fetch_package(pkg, dest, format_opts, hash="sha256"):
    """downloads a release archive from github"""

    release_file = pkg["filename"].format(**format_opts)
    release_filepath = args.directory / release_file
    if release_filepath.is_file():
        this_hash = hash_file(release_filepath, hash_type=hash)
        if this_hash == pkg[hash]:
            logger.info("Re-using existing package")
            return
        else:
            logger.info("Removing partially downloaded package")
            release_filepath.unlink()

    default_url_prefix = pkg["url_prefix"] if pkg.get("url_prefix") else "releases/download/vVERSION"
    release_url = f'{pkg["url"]}/{default_url_prefix}'.replace("VERSION", pkg["version"])
    full_url = f"{release_url}/{release_file}"

    subprocess.run(["wget", full_url], cwd=dest, check=True)
    this_hash = hash_file(release_filepath, hash_type=hash)
    if this_hash != pkg[hash]:
        raise Exception(f"Checksum mismatch on {release_file}. Expected {pkg[hash]}, but got {this_hash}")


###


if __name__ == "__main__":
    main()
