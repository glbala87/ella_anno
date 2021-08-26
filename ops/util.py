import datetime
import hashlib
import json
import multiprocessing
from collections import OrderedDict, namedtuple
from collections.abc import Mapping, Sequence
from enum import Enum
from numbers import Number
from pathlib import Path
from typing import NamedTuple, Optional, Union, overload

StrMap = Mapping[str, str]
NestedStrMap = Mapping[str, Union[str, StrMap]]


class HashType(str, Enum):
    md5 = "MD5SUM"
    sha256 = "SHA256SUM"

    def __str__(self) -> str:
        return self.name


class FileHash(NamedTuple):
    path: str
    hash: str


@overload
def format_obj(obj: str, format_opts: StrMap) -> str:
    ...


@overload
def format_obj(obj: Sequence[str], format_opts: StrMap) -> Sequence[str]:
    ...


@overload
def format_obj(obj: NestedStrMap, format_opts: StrMap) -> NestedStrMap:
    ...


@overload
def format_obj(obj: Number, format_opts: StrMap) -> Number:
    ...


def format_obj(obj, format_opts):
    """
    recursively formats all strings with a dict of replacement values
    """
    if isinstance(obj, str):
        return obj.format(**format_opts)
    elif isinstance(obj, (list, set, tuple)):
        # get list-like class to cast output to
        listy = type(obj)
        return listy([format_obj(x, format_opts) for x in obj])
    elif isinstance(obj, OrderedDict):
        new_dict = OrderedDict()
        for key, val in obj.items():
            new_dict[format_obj(key, format_opts)] = format_obj(val, format_opts)
        return new_dict
    elif isinstance(obj, dict):
        return {
            format_obj(key, format_opts): format_obj(val, format_opts) for key, val in obj.items()
        }
    elif isinstance(obj, Number):
        return obj
    else:
        raise ValueError(f"Cannot format {type(obj)}: {obj}")


def hash_file(filename: str, hash_type: HashType, block_size: int = 4096) -> str:
    """returns a checksum of the specified file"""
    file_hash = hashlib.new(hash_type.name)
    with open(filename, "rb") as file:
        for block in iter(lambda: file.read(block_size), b""):
            file_hash.update(block)
    return file_hash.hexdigest()


def hash_directory(basepath: Path, ignore: list[str] = [], **kwargs) -> list[FileHash]:
    """returns a list of FileHash tuples with relative path and hash data for each file"""
    hash_list: list[FileHash] = list()
    for file_path in basepath.rglob("*"):
        if file_path.is_dir() or file_path.name in ignore:
            continue
        filename = f"{file_path.relative_to(basepath)}"
        filehash = hash_file(filename, **kwargs)
        hash_list.append(FileHash(filename, filehash))
    return hash_list


def hash_directory_async(
    basepath: Path,
    max_procs: Optional[int] = None,
    ignore: Optional[list[str]] = None,
    *args,
    **kwargs,
) -> list[FileHash]:
    """
    returns a list of FileHash tuples with relative path and hash data for each file, in max_procs processes
    max_procs of None defaults to os.cpu_count()
    """
    ignore_files: set[str] = set([t.value.lower() for t in HashType])
    if ignore:
        ignore_files |= set([i.lower() for i in ignore])

    hash_list = list()
    file_list = [
        x for x in basepath.rglob("*") if x.is_file() and x.name.lower() not in ignore_files
    ]
    total_files = len(file_list)
    with multiprocessing.Pool(processes=max_procs) as pool:
        async_result = list()
        for file_path in file_list:
            if file_path.name.lower() == kwargs["hash_type"].value:
                # skip MD5SUM, SHA256SUM, etc.
                continue
            async_result.append(
                (
                    f"{file_path.relative_to(basepath)}",
                    pool.apply_async(_apply_hash, [file_path, args, kwargs]),
                )
            )
        finished_count = 0
        for r in async_result:
            hash_list.append(FileHash(r[0], r[1].get()))
            finished_count += 1
            if _show_status(finished_count, total_files):
                print(
                    f"{datetime.datetime.now()} - Finished hashing {r[0]} {finished_count}/{total_files} files "
                    f"({finished_count/total_files*100:.2f}%)"
                )
        hash_list = [FileHash(r[0], r[1].get()) for r in async_result]
    return hash_list


def _apply_hash(filename: str, args: Optional[list] = None, kwargs: Optional[dict] = None):
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}
    return hash_file(filename, *args, **kwargs)


def _show_status(file_num: int, max_files: int) -> bool:
    """
    returns true if it should print a status update on processing the files. this happens when `max_filse` < `max_file_limit`
    or when `file_num` is X percent (`status_mult`) of the total files to be processed (`max_files`)
    """
    max_file_limit = 50
    status_mult = 0.05
    return (
        max_files <= max_file_limit
        or file_num % int(max_files * status_mult) == 0
        or file_num == max_files
    )


class AnnoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # use default string format for date/datetime objs
        if isinstance(obj, datetime.date):
            return f"{obj}"
        return json.JSONEncoder.default(self, obj)
