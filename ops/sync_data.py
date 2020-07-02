#!/usr/bin/env python3

import argparse
import atexit
from collections import OrderedDict
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import logging

# set up logging before anything else touches it
log_format = "%(asctime)s - %(module)s - %(funcName)s:%(lineno)d - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger = logging.getLogger(__name__)

from data_spaces import DataManager
from install_thirdparty import thirdparty_packages
import time
import toml
from util import hash_directory_async, AnnoJSONEncoder, format_obj
from yaml import load as load_yaml, dump as dump_yaml

# try to use libyaml, then fall back to pure python if not available
try:
    # we're using C/BaseLoader to ensure all values are strings as expected
    from yaml import CBaseLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import BaseLoader as Loader, Dumper

atexit.register(logging.shutdown)

this_dir = Path(__file__).parent.absolute()
default_base_dir = this_dir.parent
# check for ANNO_DATA env variable, otherwise use {default_base_dir}/data
default_data_dir = Path(os.environ["ANNO_DATA"]) if os.environ.get("ANNO") else default_base_dir / "data"
default_rawdata_dir = default_base_dir / "rawdata"
default_thirdparty_dir = default_base_dir / "thirdparty"
default_dataset_file = this_dir / "datasets.json"
default_spaces_config = this_dir / "spaces_config.json"
TOUCHFILE = "DATA_READY"


def main():
    """Generate, download or upload datasets based on steps given in --dataset-file."""
    # add --validate, to check existing data/versions against sources.json, run at startup
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
        help=f"max number of processes to run in parallel. Default: {min(os.cpu_count(), 20)}",
    )
    parser.add_argument(
        "-c",
        "--spaces-config",
        type=Path,
        default=default_spaces_config,
        help=f"JSON config for spaces.DataManager. Default: {default_spaces_config}",
    )
    parser.add_argument("--cleanup", action="store_true", help="clean up raw data after successful processing")
    parser.add_argument("--skip-validation", action="store_true", help="skip md5 validation of downloaded files")
    parser.add_argument("--verbose", action="store_true", help="be extra chatty")
    parser.add_argument("--debug", action="store_true", help="run in debug mode")
    args = parser.parse_args()

    h = logging.FileHandler(args.data_dir / "SYNC_DATA_LOG")
    h.setFormatter(logging.Formatter(log_format))
    logger.addHandler(h)

    # process args
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

    if args.spaces_config.exists():
        try:
            spaces_config = json.loads(args.spaces_config.read_text())
        except Exception as e:
            logging.error(f"Failed to parse spaces config file: {args.spaces_config}")
            raise e
    else:
        raise FileNotFoundError(f"Specified --spaces-config {args.spaces_config} does not exist")
    spaces_config["skip_validation"] = args.skip_validation

    if args.generate:
        verb = "Generating"
    elif args.download:
        verb = "Downloading"
    else:
        verb = "Uploading"

    # now we actually start doing things
    sources_json_file = args.data_dir / "sources.json"
    vcfanno_toml_file = args.data_dir / "vcfanno_config.toml"

    errs = list()
    for dataset_name, dataset in sync_datasets.items():
        logger.info(f"{verb} dataset {dataset_name}")
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
            "destination": dataset.get("destination", dataset_name),
            # vep version is a special case, since data is retrieved after installing the software in `install_thirdparty.py`
            "vep_version": thirdparty_packages["vep"]["version"],
            # misc settings
            "max_procs": args.max_processes,
        }
        if dataset.get("vars"):
            format_opts.update(dataset["vars"])

        sources_data = {"version": dataset_version}
        if "hash" in dataset:
            format_opts["hash_type"] = dataset["hash"]["type"]
            format_opts["hash_value"] = dataset["hash"]["value"]

        if args.generate:
            dataset_ready = data_dir / TOUCHFILE
            if dataset_ready.exists():
                dataset_metadata = load_yaml(dataset_ready.open("rt"), Loader=Loader)
                if dataset_metadata.get("version", "") == dataset_version:
                    logger.info(f"Dataset {dataset_name} already complete, skipping\n")
                else:
                    logger.error(
                        f"Found existing {dataset_name} version {dataset_metadata['version']}, but trying to generate version {dataset_version}. Please delete {data_dir.relative_to(default_base_dir)} and try again."
                    )
                continue
            elif not data_dir.exists():
                data_dir.mkdir(parents=True)

            if not raw_dir.exists():
                raw_dir.mkdir(parents=True)

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
                    step_resp = subprocess.run(
                        step_str,
                        shell=True,
                        cwd=raw_dir,
                        stdout=h.stream,
                        stderr=subprocess.PIPE,
                        executable="/bin/bash",
                    )
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
                dump_yaml(sources_data, dataset_ready.open("wt"), Dumper=Dumper)

            if args.cleanup:
                shutil.rmtree(raw_dir)
        elif args.download or args.upload:
            mgr = DataManager(**spaces_config)
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
                update_vcfanno_toml(dataset_name, dataset, sources_data["vcfanno"], vcfanno_toml_file)
            update_sources(sources_json_file, dataset_name, sources_data)

    if errs:
        logger.error(f"Encountered errors with the following datasets:")
        for err_entry in errs:
            print(" --- ".join([str(x) for x in err_entry]))
            print(" ---\n")


def update_sources(sources_file, source_name, source_data):
    """Update sources.json file with dataset metadata."""
    if sources_file.exists():
        file_json = json.loads(sources_file.read_text(), object_pairs_hook=OrderedDict)
    else:
        file_json = OrderedDict()

    old_data = file_json.get(source_name, OrderedDict())
    if source_data != old_data:
        file_json[source_name] = source_data
        sources_file.write_text(json.dumps(file_json, cls=AnnoJSONEncoder, indent=2) + "\n")
        logger.info(f"Updated  {sources_file} for {source_name} (version: {source_data.get('version', 'N/A')})")
    else:
        logger.info(f"Not updating {sources_file} for {source_name}: data is unchanged")


def update_vcfanno_toml(dataset_name, dataset, vcfanno_entries, toml_file):
    """Update vcfanno_config.toml for the given dataset."""
    if toml_file.exists():
        toml_data = toml.loads(toml_file.read_text(), _dict=OrderedDict)
    else:
        toml_data = OrderedDict()

    # some datasets may have multiple files to be added (e.g., gnomAD), so update each of those individually
    for i, anno_entry in enumerate(vcfanno_entries):
        exact_match = False
        anno_index = None
        fuzzy_matches = []
        old_version = None

        # check if existing entries
        if "annotation" in toml_data.keys():
            # check for exact filename match to update vcfanno data if needed
            matching_index = [i for i, x in enumerate(toml_data["annotation"]) if x["file"] == anno_entry["file"]]
            if len(matching_index):
                anno_index = matching_index[0]
                exact_match = True
            else:
                # if no exact match, try for a fuzzy match by removing the version and everything afterwards
                re_filename = dataset["vcfanno"][i]["file"].format(
                    destination=dataset.get("destination", dataset_name), version="(.*?)"
                )
                for i, anno_data in enumerate(toml_data["annotation"]):
                    fuzzy_match = re.match(re_filename, anno_data["file"])
                    if fuzzy_match:
                        # if version capture group is empty, it will be None but index will still exist
                        # If old_version stays None, it suggests a poorly formatted filename in the toml
                        fuzzy_matches.append((i, fuzzy_match.groups(0)))
        else:
            toml_data["annotation"] = list()

        # bail if multiple files match, otherwise set anno_index and old_version appropriately
        if not exact_match and fuzzy_matches:
            if len(fuzzy_matches) > 1:
                err_str = f"Found {len(fuzzy_matches)} possible file matches for {dataset_name}: "
                err_str += ", ".join([toml_data["annotation"][x[0]]["file"] for x in fuzzy_matches])
                raise RuntimeError(err_str)
            else:
                anno_index, old_version = fuzzy_matches[0]

        rewrite_file = False
        if anno_index is not None:
            if exact_match and toml_data["annotation"][anno_index] == anno_entry:
                # filename matches, vcfanno config matches, do nothing
                logger.info(
                    f"Not updating {dataset_name} (version {dataset['version']}) entry in {toml_file}: data is unchanged"
                )
            else:
                # vcfanno config has changed, but filename hasn't
                if exact_match:
                    logger.info(f"Updating existing {dataset_name} entry in {toml_file} with new config")
                    rewrite_file = True
                else:
                    # filename changed version, report old_version if found or old file otherwise
                    if old_version:
                        logger.info(
                            f"Updating existing {dataset_name} entry in {toml_file} from "
                            f"{old_version} to {dataset['version']}"
                        )
                    else:
                        logger.info(
                            f"Updating existing {dataset_name} entry in {toml_file} from "
                            f"{toml_data['annotation'][anno_index]['file']} to {anno_entry['file']}"
                        )
                rewrite_file = True
                toml_data["annotation"][anno_index] = anno_entry
        else:
            # append new file data
            logger.info(f"Creating new entry for {dataset_name} in {toml_file} as {anno_entry['file']}")
            toml_data["annotation"].append(anno_entry)
            rewrite_file = True

        # rewrite toml file
        if rewrite_file:
            try:
                toml_file.write_text(toml.dumps(toml_data))
                logger.info(f"Updated {toml_file} successfully")
            except IOError as e:
                logger.error(f"Error writing to {toml_file}")
                raise e


###


if __name__ == "__main__":
    main()
