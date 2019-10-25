#!/usr/bin/env python3

import argparse
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import subprocess

import pdb

args = None
this_dir = Path().absolute()
default_base_dir = this_dir.parent
default_data_dir = default_base_dir / "data"
default_rawdata_dir = default_base_dir / "rawdata"
datasets = OrderedDict(
    [
        (
            "fasta",
            {
                "description": "reference genome from Broad in gzipped fasta",
                "version": "GRCh37",
                "hash": {"type": "md5", "value": "dd05833f18c22cc501e3e31406d140b0"},
                "destination": "FASTA",
                "download": [
                    "wget ftp://gsapubftp-anonymous@ftp.broadinstitute.org/bundle/b37/human_g1k_v37_decoy.fasta.gz",
                    "wget ftp://gsapubftp-anonymous@ftp.broadinstitute.org/bundle/b37/human_g1k_v37_decoy.fasta.gz.tbi",
                ],
                "generate": "download",
            },
        ),
        (
            "refgene",
            {
                "description": "refGene database for slicing gnomAD data",
                "version": "hg19",
                "hash": {},
                "destination": "refGene",
                "generate": [
                    "wget http://hgdownload.soe.ucsc.edu/goldenPath/hg19/database/refGene.txt.gz",
                    "zcat refGene.txt.gz | cut -f 3,5,6 | sed 's/chr//g' | sort -k1,1V -k2,2n | uniq > refgene_VERSION.bed",
                    "mysql --user=genome --host=genome-mysql.cse.ucsc.edu -A -e 'select chrom, size from VERSION.chromInfo' > data/VERSION.genome",
                    "bedtools slop -i refgene_VERSION.bed -g VERSION.genome -b 10000 > refgene_VERSION_slop_10k.bed",
                    "rm refGene.txt.gz",
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
        ("clinvar", {"description": "clinvar variant database", "version": "20190628", "generate": []}),
        ("hgmd", {"description": "HGMD variant database (license required)", "version": "2019.2", "generate": []}),
        ("exac", {"description": "", "version": "r0.3.1", "generate": []}),
    ]
)


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
        metavar="/path/to/data/dir",
        type=Path,
        default=default_data_dir,
        help="directory to write processed data to",
    )
    parser.add_argument(
        "-rd",
        "--rawdata-dir",
        metavar="/path/to/rawdata/dir",
        type=Path,
        default=default_rawdata_dir,
        help="directory to temporarily store unprocessed data in",
    )
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
        raw_dir = args.rawdata_dir / dataset_name
        data_dir = args.data_dir / dataset.get("destination", dataset_name).replace(
            "VERSION", dataset.get("version", "")
        )

        if args.generate:
            if not raw_dir.exists():
                raw_dir.mkdir(parents=True)

            for step_num, step in enumerate(dataset["generate"]):
                if args.debug:
                    print(f"DEBUG - Step {step_num}: {step}\n")
                step_resp = subprocess.run(step, shell=True, cwd=raw_dir)
                if step_resp.returncode != 0:
                    raise Exception(f"Error installing package {pkg_name} on step: {step}")
        else:
            raise NotImplemented()


###


if __name__ == "__main__":
    main()
