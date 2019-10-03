#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess

thirdparty_packages = {
    "htslib": {
        "url": "https://github.com/samtools/htslib",
        "version": "1.9",
        "sha256": "",
        "filename": "htslib-VERSION.tar.bz2",
        "src_dir": "htslib-VERSION",
        "installation": [
            "autoheader",
            "autoconf",
            "./configure",
            "make",
            "make install"
        ],
    },
    "vcfanno": {
        "url": "https://github.com/brentp/vcfanno",
        "version": "0.2.8",
        "sha256": "",
        "download": {"filename": ""},
    },
    "bedtools": {
        "url": "https://github.com/brentp/vcfanno",
        "version": "2.19.1",
        "sha256": "",
    },
    "vcftools": {
        "url": "https://github.com/vcftools/vcftools",
        "version": "0.1.16",
        "sha256": "",
    },
    "vep": {
        "url": "https://github.com/Ensembl/ensembl-vep",
        "version": "79",
        "sha256": "",
    },
    "vt": {"url": "https://github.com/atks/vt", "version": "0.57721", "sha256": ""},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory",
        "-d",
        default=os.path.join(os.getcwd(), "thirdparty"),
        help="directory to extract the thirdparty packages into",
    )
    parser.add_argument("--verbose", action="store_true", help="be extra chatty")
    parser.add_argument("--debug", action="store_true", help="run in debug mode")
    args = parser.parse_args()

    if args.debug:
        setattr(args, "verbose", True)

    if not os.path.exists(args.directory):
        os.makedirs(args.directory)

    for pkg_name, pkg in thirdparty_packages.items():
        pkg_artifact = pkg["filename"].replace("VERSION", pkg["version"])
        pkg_dir = pkg["src_dir"].replace("VERSION", pkg["version"])
        if args.verbose:
            print(f"Fetching {pkg_name}")
        github_fetch_package(pkg, args.directory, args.verbose, args.debug)

        if args.verbose:
            print(f"Compiling / packaging {pkg_name}")
        untar_resp = subprocess.run(
            ["tar", "xvf", pkg_artifact],
            cwd=args.directory,
        )
        if untar_resp.returncode != 0:
            raise Exception(
                f"Error extracting package {pkg['filename']}: {untar_resp.returncode}"
            )
        os.remove(os.path.join(args.directory, pkg_artifact))

        compile_dir = os.path.join(args.directory, pkg_dir)
        for step_num, step in enumerate(pkg["installation"]):
            if args.debug:
                print(f"DEBUG - Step {step_num}: {step}\n")
            subprocess.run(step.split(), cwd=compile_dir)
        if args.debug:
            break


def github_fetch_package(pkg, dest, verbose=False, debug=False):
    release_url = f'{pkg["url"]}/releases/download/{pkg["version"]}'
    release_file = pkg["filename"].replace("VERSION", pkg["version"])
    full_url = f"{release_url}/{release_file}"
    mkdir_resp = subprocess.run(["mktemp", "-d"], capture_output=True)
    wget_cwd = mkdir_resp.stdout.decode().strip()
    if debug:
        print(f"Created tmp dir: {wget_cwd}")
    fetch_result = subprocess.run(["wget", full_url], cwd=wget_cwd)
    if fetch_result.returncode == 0:
        shutil.move(
            os.path.join(wget_cwd, release_file), os.path.join(dest, release_file)
        )
        os.rmdir(wget_cwd)
    else:
        raise Exception(
            f"Failed to fetch package file {full_url}: return code: {fetch_result.returncode}"
        )


###


if __name__ == "__main__":
    main()
