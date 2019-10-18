#!/usr/bin/env python3

import argparse
from collections import OrderedDict
import hashlib
import os
import subprocess

args = None
datasets = OrderedDict(
    [
        (
            "fasta",
            {
                "description": "reference genome from Broad in gzipped fasta",
                "version": "GRCh37",
                "hash": {"type": "md5", "value": "dd05833f18c22cc501e3e31406d140b0"},
                "destination": "FASTA",
                "actions": [
                    "wget ftp://gsapubftp-anonymous@ftp.broadinstitute.org/bundle/b37/human_g1k_v37_decoy.fasta.gz"
                ],
            },
        ),
        (
            "gnomad",
            {
                "description": "gnomaAD variant database",
                "version": "2.0.2",
                "actions": ["scripts/download_gnomad.sh -r VERSION GNOMAD_OPTS"],
            },
        ),
        ("clinvar", {"description": "clinvar variant database", "version": "20190628", "actions": []}),
        ("hgmd", {"description": "HGMD variant database (license required)", "version": "2019.2", "actions": []}),
        ("exac", {"description": "", "version": "r0.3.1", "actions": []}),
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
    parser.add_argument("-b", "--basedir", default="", help="base data directory")
    parser.add_argument("--verbose", action="store_true", help="be extra chatty")
    parser.add_argument("--debug", action="store_true", help="run in debug mode")
    args = parser.parse_args()

    if args.debug:
        setattr(args, "verbose", True)

    if args.dataset:
        sync_datasets = [dict(args.dataset, datasets[args.dataset])]
    else:
        sync_datasets = datasets

    for dataset_name, dataset in sync_datasets.items():
        print("Syncing dataset {}".format(dataset_name))


###


if __name__ == "__main__":
    main()
