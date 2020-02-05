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
import toml
from util import hash_file, hash_directory_async, AnnoJSONEncoder, format_obj
from yaml import load as load_yaml, dump as dump_yaml

try:
    # try to use libyaml first
    from yaml import CBaseLoader as Loader, CDumper as Dumper
except ImportError:
    # fall back to pure python
    from yaml import BaseLoader as Loader, Dumper
# we're using C/BaseLoader to ensure all values are strings as expected

import pdb

this_dir = Path(__file__).parent.absolute()
default_base_dir = this_dir.parent
# check for ANNO_DATA env variable, otherwise use {default_base_dir}/data
default_data_dir = Path(os.environ["ANNO_DATA"]) if os.environ.get("ANNO") else default_base_dir / "data"
default_rawdata_dir = default_base_dir / "rawdata"
default_thirdparty_dir = default_base_dir / "thirdparty"
default_dataset_file = this_dir / "datasets.json"
TOUCHFILE = "DATA_READY"

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
        "-f",
        "--dataset-file",
        type=Path,
        default=default_dataset_file,
        help=f"JSON file containing dataset info. Default: {default_dataset_file}",
    )
    parser.add_argument("-d", "--dataset", help="download or generate a specific dataset")
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
    parser.add_argument("--skip-validation", action="store_true", help="skip md5 validation of downloaded files")
    parser.add_argument("--verbose", action="store_true", help="be extra chatty")
    parser.add_argument("--debug", action="store_true", help="run in debug mode")
    args = parser.parse_args()

    if args.debug:
        setattr(args, "verbose", True)

    if args.dataset_file.exists():
        datasets = json.loads(args.dataset_file.read_text(), object_pairs_hook=OrderedDict)
    else:
        raise IOError(f"Cannot read dataset file: {args.dataset_file}. Check it exists, is readable and try again")

    if args.dataset and args.dataset not in datasets.keys():
        raise ValueError(f"Invalid dataset: {args.dataset}. Must be one of: {', '.join(sorted(datasets.keys()))}")

    if args.dataset:
        sync_datasets = {args.dataset: datasets[args.dataset]}
    else:
        sync_datasets = datasets

    sources_json_file = args.data_dir / "sources.json"
    vcfanno_toml_file = args.data_dir / "vcfanno_config.toml"

    errs = list()
    for dataset_name, dataset in sync_datasets.items():
        logger.info(f"Syncing dataset {dataset_name}")
        raw_dir = args.rawdata_dir.absolute() / dataset_name
        data_dir = args.data_dir.absolute() / dataset.get("destination", dataset_name)
        thirdparty_dir = args.thirdparty_dir.absolute() / dataset.get("thirdparty-name", dataset_name)
        if dataset_name == "vep":
            # special processing for VEP, which has its version defined in install_thirdparty.py
            dataset_version = thirdparty_packages["vep"]["version"]
        else:
            dataset_version = dataset.get("version", "")

        format_opts = {
            # directory paths, all absolute
            "root_dir": str(default_base_dir),
            "base_data_dir": str(args.data_dir.absolute()),
            "data_dir": str(data_dir),
            "thirdparty": str(thirdparty_dir),
            # version info
            "version": dataset_version,
            # vep version is a special case, since data is retrieved after installing the software in `install_thirdparty.py`
            "vep_version": thirdparty_packages["vep"]["version"],
            # misc settings
            "max_procs": args.max_processes,
        }

        sources_data = OrderedDict()
        sources_data["version"] = dataset_version
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
                step_str = format_obj(step, format_opts)

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
                fin_time = datetime.datetime.utcnow()
                sources_data["timestamp"] = fin_time
                dump_yaml(sources_data.open("wt"), Dumper=Dumper)

            if args.cleanup:
                shutil.rmtree(raw_dir)
        elif args.download or args.upload:
            mgr = DataManager()
            cmd_args = [dataset_name, dataset_version, data_dir.relative_to(default_base_dir)]
            if args.download:
                mgr.download_package(*cmd_args)
                dataset_touchfile = data_dir / TOUCHFILE
                dataset_metadata = load_yaml(dataset_touchfile.open("rt"), Loader=Loader)
                if dataset_metadata["version"] != dataset_version:
                    logger.error(
                        f"Downloaded data for {dataset_name} version {dataset_metadata['version']}, but expected {dataset_version}"
                    )
                    continue
                sources_data["timestamp"] = dataset_metadata["timestamp"]

                if args.skip_validation:
                    logger.info(f"Skipping download validation for {dataset_name}")
                else:
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

        if args.generate or args.download:
            if "vcfanno" in dataset:
                sources_data["vcfanno"] = format_obj(dataset["vcfanno"], format_opts)
                update_vcfanno_toml(vcfanno_toml_file, sources_data["vcfanno"])
            update_sources(sources_json_file, dataset_name, sources_data)

    if errs:
        logger.error(f"Encountered errors with the following datasets:")
        for err_entry in errs:
            print(" --- ".join([str(x) for x in err_entry]))
            print(" ---\n")


def update_sources(sources_file, source_name, source_data):
    if sources_file.exists():
        file_json = json.loads(sources_file.read_text(), object_pairs_hook=OrderedDict)
    else:
        file_json = OrderedDict()

    old_data = file_json.get(source_name, OrderedDict())
    if source_data != old_data:
        file_json[source_name] = source_data
        sources_file.write_text(json.dumps(file_json, cls=AnnoJSONEncoder, indent=2) + "\n")
    else:
        logger.info(f"Not updating {sources_file} for {source_name}: data is unchanged")


def update_vcfanno_toml(toml_file, annotation_data):
    if toml_file.exists():
        toml_data = toml.loads(toml_file.read_text(), _dict=OrderedDict)
    else:
        toml_data = OrderedDict()

    # check if entry for file already exists
    if "annotation" in toml_data.keys():
        matching_index = [i for i, x in enumerate(toml_data["annotation"]) if x["file"] == annotation_data["file"]]
        anno_index = matching_index[0] if matching_index else None
    else:
        toml_data["annotation"] = list()
        anno_index = None

    if anno_index and toml_data["annotation"][anno_index] == annotation_data:
        loggger.info(f"Not updating {toml_file} for {annotation_data['file']: data is unchanged}")
    else:
        # append new file data, otherwise update in place
        if anno_index is None:
            toml_data["annotation"].append(annotation_data)
        else:
            toml_data["annotation"][anno_index] = annotation_data

        try:
            toml_file.write_text(toml.dumps(toml_data))
        except IOError as e:
            logger.error(f"Error writing to {toml_file}")
            raise e


###


if __name__ == "__main__":
    main()
