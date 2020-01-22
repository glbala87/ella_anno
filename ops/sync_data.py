#!/usr/bin/env python3

import argparse
from collections import OrderedDict
import datetime
import hashlib
import json
import os
import logging
from pathlib import Path
import shutil
import subprocess
from spaces import DataManager
from install_thirdparty import thirdparty_packages
import time
from util import hash_file, hash_directory_async

import pdb

this_dir = Path(__file__).parent.absolute()
default_base_dir = this_dir.parent
default_data_dir = default_base_dir / "data"
default_rawdata_dir = default_base_dir / "rawdata"
default_thirdparty_dir = default_base_dir / "thirdparty"
datasets = OrderedDict(
    [
        (
            "fasta",
            {
                "description": "reference genome from Broad in gzipped fasta",
                "version": "GRCh37",
                "hash": {"type": "md5", "value": "dd05833f18c22cc501e3e31406d140b0"},
                "destination": "FASTA",
                "retries": 5,
                "generate": [
                    "wget ftp://gsapubftp-anonymous@ftp.broadinstitute.org/bundle/b37/human_g1k_v37_decoy.fasta.gz -O {data_dir}/human_g1k_v37_decoy.fasta.gz",
                    "echo '{hash_value} {data_dir}/human_g1k_v37_decoy.fasta.gz' | {hash_type}sum -c",
                    "gunzip {data_dir}/human_g1k_v37_decoy.fasta.gz",
                    "bgzip {data_dir}/human_g1k_v37_decoy.fasta -c > {data_dir}/human_g1k_v37_decoy.fasta.gz",
                ],
            },
        ),
        (
            "vep",
            {
                "description": "offline VEP cache",
                "destination": "VEP/cache",
                "version": thirdparty_packages["vep"]["version"],
                "thirdparty-name": "ensembl-vep-release",
                "generate": ["perl {thirdparty}/INSTALL.pl -a cf -l -n -s homo_sapiens_merged -y GRCh37 -c {data_dir}"],
            },
        ),
        (
            "refgene",
            {
                "description": "refGene database for slicing gnomAD data",
                "version": "hg19",
                "hash": {"type": "md5", "value": "e0de330beb80dc91df475615f7181f8c"},
                "destination": "refGene",
                "generate": [
                    "wget http://hgdownload.soe.ucsc.edu/goldenPath/hg19/database/refGene.txt.gz",
                    "echo '{hash_value} refGene.txt.gz' | {hash_type}sum -c",
                    "zcat refGene.txt.gz | cut -f 3,5,6 | sed 's/chr//g' | sort -k1,1V -k2,2n | uniq | bedtools merge > refgene_{version}.bed",
                    "mysql --user=genome --host=genome-mysql.cse.ucsc.edu -A -e 'select chrom, size from {version}.chromInfo' | sed 's/chr//g' > {data_dir}/{version}.genome",
                    "bedtools slop -i refgene_{version}.bed -g {data_dir}/{version}.genome -b 10000 > {data_dir}/refgene_{version}_slop_10k.bed",
                ],
            },
        ),
        (
            "gnomad",
            {
                "description": "gnomAD variant database",
                "version": "2.0.2",
                "destination": "variantDBs/gnomAD",
                "generate": [
                    "{base_dir}/scripts/gnomad/download_gnomad.sh -r {version} -s",
                    "{base_dir}/scripts/gnomad/gnomad_process_data.sh -v {version} -b {base_dir}/data/refGene/refgene_hg19_slop_10k.bed",
                ],
            },
        ),
        (
            "clinvar",
            {
                "description": "clinvar variant database",
                "version": "20191127",
                "destination": "variantDBs/clinvar",
                "generate": [
                    "python {base_dir}/scripts/clinvar/clinvardb_to_vcf.py -np {max_procs} -o {data_dir}/clinvar_{version}.vcf -g {base_dir}/data/FASTA/human_g1k_v37_decoy.fasta"
                ],
            },
        ),
        (
            "seqrepo",
            {
                "description": "biocommons seqrepo data",
                "version": "2019-06-20",
                "destination": "seqrepo",
                "generate": [
                    "seqrepo -r {data_dir} -v pull --instance-name {version}",
                    "[[ -d {data_dir}/{version} ]] || (echo downloaded version does not match; exit 1)",
                ],
            },
        ),
        # ("hgmd", {"description": "HGMD variant database (license required)", "version": "2019.2", "generate": []}),
    ]
)
TOUCHFILE = "DATA_READY"
sources_json_file = default_base_dir / "sources.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# add --validate, to check existing data/versions against sources.json, run at startup


def main():
    parser = argparse.ArgumentParser()
    action_args = parser.add_mutually_exclusive_group(required=True)
    action_args.add_argument("--download", action="store_true", help="download pre-processed datasets")
    action_args.add_argument("--generate", action="store_true", help="generate processed datasets")
    action_args.add_argument("--upload", action="store_true", help="upload generated data to cloud storage")
    parser.add_argument(
        "-d", "--dataset", choices=list(datasets.keys()), help="download or generate a specific dataset"
    )
    parser.add_argument(
        "-dd",
        "--data-dir",
        metavar="/path/to/anno/data/dir",
        type=Path,
        default=default_data_dir,
        help=f"directory to write processed data to. Default: {default_data_dir}",
    )
    parser.add_argument(
        "-rd",
        "--rawdata-dir",
        metavar="/path/to/anno/rawdata",
        type=Path,
        default=default_rawdata_dir,
        help=f"directory to temporarily store unprocessed data in. Default: {default_rawdata_dir}",
    )
    parser.add_argument(
        "-tp",
        "--thirdparty-dir",
        metavar="/path/to/anno/thirdparty",
        type=Path,
        default=default_thirdparty_dir,
        help=f"directory thirdparty packages are installed in. Default: {default_thirdparty_dir}",
    )
    parser.add_argument(
        "--max-processes",
        "-x",
        type=int,
        default=min(os.cpu_count(), 20),
        help=f"max number of processes to run in parallel. Default: {os.cpu_count()}",
    )
    parser.add_argument("--cleanup", action="store_true", help="clean up raw data after successful processing")
    parser.add_argument("--verbose", action="store_true", help="be extra chatty")
    parser.add_argument("--debug", action="store_true", help="run in debug mode")
    args = parser.parse_args()

    if args.debug:
        setattr(args, "verbose", True)

    if args.dataset:
        sync_datasets = {args.dataset: datasets[args.dataset]}
    else:
        sync_datasets = datasets

    errs = list()
    for dataset_name, dataset in sync_datasets.items():
        logger.info(f"Syncing dataset {dataset_name}")
        raw_dir = args.rawdata_dir.absolute() / dataset_name
        data_dir = args.data_dir.absolute() / dataset.get("destination", dataset_name)
        thirdparty_dir = args.thirdparty_dir.absolute() / dataset.get("thirdparty-name", dataset_name)
        dataset_version = dataset.get("version", "")
        format_opts = {
            "version": dataset_version,
            "data_dir": str(data_dir),
            "thirdparty": str(thirdparty_dir),
            "base_dir": str(default_base_dir),
            "max_procs": args.max_processes,
        }
        if "hash" in dataset:
            format_opts["hash_type"] = dataset["hash"]["type"]
            format_opts["hash_value"] = dataset["hash"]["value"]

        if args.generate:
            dataset_ready = data_dir / TOUCHFILE
            if dataset_ready.exists():
                logger.info(f"Dataset {dataset_name} already complete, skipping\n")
                continue
            elif not data_dir.exists():
                data_dir.mkdir(parents=True)

            if not raw_dir.exists():
                raw_dir.mkdir(parents=True)

            if type(dataset["generate"]) is str and dataset["generate"] == "download":
                dataset["generate"] = dataset["download"]

            for step_num, step in enumerate(dataset["generate"]):
                logger.debug(f"DEBUG - Step {step_num}: {step}\n")
                step_str = step.format(**format_opts)

                # if dataset allows retries (e.g., Broad's crappy FTP server), retry until max reached
                # otherwise, bail on error
                num_retries = 0
                max_retries = dataset.get("retries", 0)
                step_success = False
                while num_retries <= max_retries:
                    logger.info(f"Running: {step_str}")
                    step_resp = subprocess.run(step_str, shell=True, cwd=raw_dir, stderr=subprocess.PIPE)
                    if step_resp.returncode != 0:
                        errs.append((dataset_name, step_str, step_resp.returncode, step_resp.stderr.decode("utf-8")))
                        if num_retries >= max_retries and max_retries > 0:
                            errs.append((dataset_name, "max retries exceeded without success"))
                            break
                        else:
                            num_retries += 1
                            time.sleep(1 * num_retries)
                    else:
                        step_success = True
                        break

                # if one step fails max retries, abort processing
                if step_success is False:
                    break

            # generate md5s for each file
            md5sum_file = data_dir / "MD5SUM"
            file_hashes = hash_directory_async(data_dir)
            with md5sum_file.open("wt") as md5_output:
                for file in sorted(file_hashes, key=lambda x: x.path):
                    print(f"{file.hash}\t{file.path}", file=md5_output)

            # only write if process finished successfully
            if step_success is True:
                dataset_ready.write_text(f"Generated: {datetime.datetime.utcnow()}\n")
                dataset_ready.write_text(f"Version: {dataset_version}\n")

            if args.cleanup:
                shutil.rmtree(raw_dir)
        elif args.download or args.upload:
            mgr = DataManager()
            cmd_args = [dataset_name, dataset_version, data_dir.relative_to(default_base_dir)]
            if args.download:
                mgr.download_package(*cmd_args)

                logger.info("Validating downloaded data")
                md5sum = data_dir / "MD5SUM"
                if not md5sum.exists():
                    logger.error(f"No MD5SUM file found for {dataset_name} at {md5sum}, cannot validate files")
                    continue
                subprocess.run(["md5sum", "--quiet", "-c", "MD5SUM"], cwd=data_dir, check=True)
                logger.info(f"All {dataset_name} files validated successfully")
            else:
                mgr.upload_package(*cmd_args)
        else:
            raise Exception("This should never happen, what did you do?!")

    if errs:
        logger.error(f"Encountered errors with the following datasets:")
        for err_entry in errs:
            print(" --- ".join([str(x) for x in err_entry]))
            print(" ---\n")


def update_sources(key, val):
    file_json = json.loads(sources_json_file.read_text())
    file_json[key] = val
    sources_json_file.write_text(json.dumps(file_json, indent=2, sort_keys=True) + "\n")


###


if __name__ == "__main__":
    main()
