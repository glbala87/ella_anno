from collections import namedtuple
import datetime
import hashlib
import multiprocessing
import os
from pathlib import Path
import re
import sys


FileHash = namedtuple("FileHash", ["path", "hash"])
DEFAULT_HASH_TYPE = "md5"
DEFAULT_BLOCK_SIZE = 4096


def hash_file(filename, hash_type=DEFAULT_HASH_TYPE, block_size=DEFAULT_BLOCK_SIZE):
    """returns a checksum of the specified file"""
    file_hash = hashlib.new(hash_type)
    with open(filename, "rb") as file:
        for block in iter(lambda: file.read(block_size), b""):
            file_hash.update(block)
    return file_hash.hexdigest()


def hash_directory(basepath, ignore=[], **kwargs):
    """returns a list of FileHash tuples with relative path and hash data for each file"""
    hash_list = list()
    for file_path in basepath.rglob("*"):
        if file_path.is_dir() or file_path.name in ignore:
            continue
        filename = f"{file_path.relative_to(basepath)}"
        filehash = hash_file(filename, **kwargs)
        hash_list.append(FileHash(filename, filehash))
    return hash_list


def hash_directory_async(basepath, max_procs=None, ignore=[], *args, **kwargs):
    """returns a list of FileHash tuples with relative path and hash data for each file, in max_procs processes
    max_procs of None defaults to os.cpu_count()"""

    hash_list = list()
    file_list = [x for x in basepath.rglob("*") if x.is_file() and x.name not in ignore]
    total_files = len(file_list)
    with multiprocessing.Pool(processes=max_procs) as pool:
        async_result = list()
        for file_path in file_list:
            async_result.append(
                (f"{file_path.relative_to(basepath)}", pool.apply_async(apply_hash, [file_path, args, kwargs]))
            )
        finished_count = 0
        for r in async_result:
            hash_list.append(FileHash(r[0], r[1].get()))
            finished_count += 1
            if show_status(finished_count, total_files):
                print(
                    f"{datetime.datetime.now()} - Finished hashing {r[0]} {finished_count}/{total_files} files "
                    f"({finished_count/total_files*100:.2f}%)"
                )
        hash_list = [FileHash(r[0], r[1].get()) for r in async_result]
    return hash_list


def apply_hash(filename, args=list(), kwargs=dict()):
    return hash_file(filename, *args, **kwargs)


def show_status(file_num, max_files, ceiling=50, mult=0.05):
    max_file_limit = 50
    status_mult = 0.05
    return max_files <= max_file_limit or file_num % int(max_files * status_mult) == 0 or file_num == max_files
