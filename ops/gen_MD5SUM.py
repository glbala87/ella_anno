#!/usr/bin/env python3

import argparse
import datetime
import os
from pathlib import Path
from util import hash_directory_async, hash_directory

DEFAULT_PROCS = os.cpu_count()
DEFAULT_IGNORE = ["DATA_READY", "MD5SUM"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory", type=Path, help="path to directory to generate an MD5SUM file for")
    parser.add_argument(
        "-p",
        "--processes",
        metavar="NUM_PROCS",
        type=int,
        default=DEFAULT_PROCS,
        help=f"number of processes to use. Default: {DEFAULT_PROCS}",
    )
    parser.add_argument(
        "-i",
        "--ignore",
        metavar="FILENAME",
        nargs="+",
        default=DEFAULT_IGNORE,
        help=f"names of files to skip hashing. Default: {', '.join(DEFAULT_IGNORE)}",
    )
    parser.add_argument("--verbose", action="store_true", help="be extra chatty")
    parser.add_argument("--debug", action="store_true", help="run in debug mode")
    args = parser.parse_args()

    if args.debug:
        setattr(args, "verbose", True)

    num_files = len([x for x in args.directory.rglob("*") if x.is_file() and x.name not in args.ignore])
    start_time = datetime.datetime.now()
    print(f"{start_time} - Hashing {num_files} files with {args.processes} processes")
    if args.processes > 1:
        hash_list = hash_directory_async(args.directory, max_procs=args.processes, ignore=args.ignore)
    else:
        hash_list = hash_directory(args.directory)

    md5sum = args.directory / "MD5SUM"
    print(f"{datetime.datetime.now()} - Finished hashing all files, writing output to {md5sum}")
    with md5sum.open("wt") as md5_writer:
        for file in sorted(hash_list, key=lambda x: x.path):
            print(f"{file.hash}\t{file.path}", file=md5_writer)
    finish_time = datetime.datetime.now()
    print(f"{datetime.datetime.now()} - Output complete after {format_delta(finish_time - start_time)}")


def format_delta(dt_delta, show_ms=True):
    secs = dt_delta.seconds % 60
    mins = int(dt_delta.seconds / 60) % 60
    hours = int(dt_delta.seconds / 60 / 60)
    if show_ms:
        dt_str = f"{secs:02}.{dt_delta.microseconds}s"
    else:
        dt_str = f"{secs:02}s"
    if mins:
        dt_str = f"{mins:02}m{dt_str}"
    if hours:
        dt_str = f"{hours}h{dt_str}"
    return dt_str


###


if __name__ == "__main__":
    main()
