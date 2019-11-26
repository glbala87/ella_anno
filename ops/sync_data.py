#!/usr/bin/env python3

import argparse
from collections import OrderedDict
import datetime
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pdb

args = None
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
                "download": [
                    "wget ftp://gsapubftp-anonymous@ftp.broadinstitute.org/bundle/b37/human_g1k_v37_decoy.fasta.gz -O DATA_DIR/human_g1k_v37_decoy.fasta.gz",
                    "echo 'HASH_VALUE DATA_DIR/human_g1k_v37_decoy.fasta.gz' | HASH_TYPEsum -c",
                ],
                "generate": "download",
            },
        ),
        (
            "vep",
            {
                "description": "offline VEP cache",
                "version": "98.2",
                "destination": "VEP/cache",
                "thirdparty-name": "ensembl-vep-release",
                "generate": ["perl THIRDPARTY/INSTALL.pl -a cf -l -n -s homo_sapiens_merged -y GRCh37 -c DATA_DIR"],
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
                    "echo 'HASH_VALUE refGene.txt.gz' | HASH_TYPEsum -c",
                    "zcat refGene.txt.gz | cut -f 3,5,6 | sed 's/chr//g' | sort -k1,1V -k2,2n | uniq > refgene_VERSION.bed",
                    "mysql --user=genome --host=genome-mysql.cse.ucsc.edu -A -e 'select chrom, size from VERSION.chromInfo' > DATA_DIR/VERSION.genome",
                    "bedtools slop -i refgene_VERSION.bed -g DATA_DIR/VERSION.genome -b 10000 > DATA_DIR/refgene_VERSION_slop_10k.bed",
                ],
            },
        ),
        (
            "gnomad",
            {
                "description": "gnomaAD variant database",
                "version": "2.0.2",
                "destination": "variantDBs/gnomAD",
                "generate": [
                    "scripts/gnomad/download_gnomad.sh -r VERSION GNOMAD_DL_OPTS",
                    "scripts/gnomad/gnomad_process_data.sh -r VERSION GNOMAD_DATA_OPTS",
                ],
            },
        ),
        (
            "clinvar",
            {
                "description": "clinvar variant database",
                "version": "20190628",
                "destination": "variantDBs/clinvar",
                "generate": [
                    "python scripts/clinvar/clinvardb_to_vcf.py -np $(($(grep -c processor /proc/cpuinfo || echo 1) * 2)) -o DATADIR/clinvar_VERSION.vcf -g data/FASTA/human_g1k_v37_decoy.fasta.gz"
                ],
            },
        ),
        (
            "seqrepo",
            {
                "description": "biocommons seqrepo data",
                "version": "latest",
                "destination": "seqrepo",
                "generate": ["seqrepo -r DATA_DIR -v pull"],
            },
        ),
        ("hgmd", {"description": "HGMD variant database (license required)", "version": "2019.2", "generate": []}),
    ]
)
TOUCHFILE = "DATA_READY"


def main():
    global args

    parser = argparse.ArgumentParser()
    action_args = parser.add_mutually_exclusive_group(required=True)
    action_args.add_argument("--download", action="store_true", help="download pre-processed datasets")
    action_args.add_argument("--generate", action="store_true", help="generate processed datasets")
    parser.add_argument(
        "-d", "--dataset", choices=list(datasets.keys()), help="download or generate a specific dataset"
    )
    parser.add_argument(
        "-dd",
        "--data-dir",
        metavar="/path/to/anno/data/dir",
        type=Path,
        default=default_data_dir,
        help="directory to write processed data to. Default: {}".format(default_data_dir),
    )
    parser.add_argument(
        "-rd",
        "--rawdata-dir",
        metavar="/path/to/anno/rawdata",
        type=Path,
        default=default_rawdata_dir,
        help="directory to temporarily store unprocessed data in. Default: {}".format(default_rawdata_dir),
    )
    parser.add_argument(
        "-tp",
        "--thirdparty-dir",
        metavar="/path/to/anno/thirdparty",
        type=Path,
        default=default_thirdparty_dir,
        help="directory thirdparty packages are installed in. Default: {}".format(default_thirdparty_dir),
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

    for dataset_name, dataset in sync_datasets.items():
        print("Syncing dataset {}".format(dataset_name))
        raw_dir = args.rawdata_dir.absolute() / dataset_name
        data_dir = args.data_dir.absolute() / dataset.get("destination", dataset_name)
        thirdparty_dir = args.thirdparty_dir.absolute() / dataset.get("thirdparty-name", dataset_name)
        evals = OrderedDict(
            [("VERSION", dataset.get("version", "")), ("DATA_DIR", str(data_dir)), ("THIRDPARTY", str(thirdparty_dir))]
        )
        if "hash" in dataset:
            evals["HASH_TYPE"] = dataset["hash"]["type"]
            evals["HASH_VALUE"] = dataset["hash"]["value"]

        if args.generate:
            dataset_ready = data_dir / TOUCHFILE
            if dataset_ready.exists():
                print(f"Dataset {dataset_name} already complete, skipping")
                continue
            elif not data_dir.exists():
                data_dir.mkdir(parents=True)

            if not raw_dir.exists():
                raw_dir.mkdir(parents=True)

            if type(dataset["generate"]) is str and dataset["generate"] == "download":
                dataset["generate"] = dataset["download"]

            for step_num, step in enumerate(dataset["generate"]):
                if args.debug:
                    print(f"DEBUG - Step {step_num}: {step}\n")

                eval_step = [step]
                for var_name, val in evals.items():
                    if var_name in eval_step[-1]:
                        eval_step.append(eval_step[-1].replace(var_name, val))

                if args.debug:
                    print(f"DEBUG - step replacements: {eval_step}")

                # if dataset allows retries (e.g., Broad's crappy FTP server), retry until max reached
                # otherwise, bail on error
                num_retries = 0
                max_retries = dataset.get("retries", 0)
                while num_retries <= max_retries:
                    step_resp = subprocess.run(eval_step[-1], shell=True, cwd=raw_dir)
                    if step_resp.returncode != 0:
                        if num_retries >= max_retries:
                            raise Exception(f"Error installing package {dataset_name} on step: {eval_step[-1]}")
                        else:
                            num_retries += 1
                    else:
                        break

            dataset_ready.write_text(f"{datetime.datetime.utcnow()}")

            if args.cleanup:
                shutil.rmtree(raw_dir)
        else:
            raise NotImplemented()


###


if __name__ == "__main__":
    main()
