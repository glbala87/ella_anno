#!/usr/bin/env python3

import datetime
import json
import re
import shutil
import sys
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from shlex import quote
from typing import Optional

REPO_ROOT = Path(__file__).parents[2]
CHECK_DIRS = ["bin", "ops", "scripts", "src", "tests"]
CHECK_PATHS = [REPO_ROOT / d for d in CHECK_DIRS]
DEVC_JSON = REPO_ROOT / ".devcontainer" / "devcontainer.json"
IGNORE_NAMES = ["MD5SUM", "DATA_READY"]
INCLUDE_SUFFIX = [".sh", ""]
RE_SHEBANG = re.compile(r"^#!/bin/(?:ba)sh\b")

###


class LinterType(str, Enum):
    shellcheck = "shellcheck"
    shfmt = "shfmt"

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}.{self.name}>"


@dataclass(frozen=True)
class LintError:
    __slots__ = ("linter", "log", "file", "rc", "cmd")
    linter: LinterType
    rc: int
    file: str
    cmd: list[str]
    log: str


@dataclass(frozen=True, init=False)
class Linter:
    __slots__ = ("_type", "params", "path")
    _type: LinterType
    params: list[str]
    path: Path

    def __init__(
        self,
        type: LinterType,
        params: Sequence[str],
        path: Optional[str] = None,
    ) -> None:
        object.__setattr__(self, "_type", type)
        object.__setattr__(self, "params", params)
        if path is None:
            path = shutil.which(type.name)
            if path is None:
                raise FileNotFoundError(f"Unable to find exectuable for {type.name}")
        object.__setattr__(self, "path", Path(path))

    @property
    def name(self) -> str:
        return self._type.name

    def run(self, file: Path) -> Optional[LintError]:
        # use shlex.quote to prevent shell injection
        cmd = [quote(c) for c in [str(self.path), *self.params, str(file)]]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if res.returncode != 0:
            return LintError(
                self._type,
                res.returncode,
                str(file.relative_to(REPO_ROOT)),
                cmd,
                res.stdout.strip(),
            )


###


def log(msg: str, err: bool = False) -> None:
    dt = datetime.datetime.now().isoformat(" ", "milliseconds")
    if err:
        log_level = "ERROR"
        output = sys.stderr
    else:
        log_level = "INFO"
        output = sys.stdout
    print(f"{dt} - {log_level} - {msg}", file=output)


def err(msg: str) -> None:
    log(msg, err=True)


###


def find_scripts() -> Sequence[Path]:
    files: list[Path] = []
    for dir in CHECK_PATHS:
        dir_files = _walk_dir(dir)
        if dir_files:
            files.extend(dir_files)
    return files


def _walk_dir(dir_name: Path) -> Sequence[Path]:
    files = []
    for child in dir_name.resolve().iterdir():
        if child.is_file():
            if child.suffix not in INCLUDE_SUFFIX or child.name in IGNORE_NAMES:
                continue
            elif child.suffix == ".sh":
                files.append(child)
            else:
                with child.open("rt") as fh:
                    try:
                        l = fh.readline()
                    except UnicodeDecodeError:
                        log(f"skipping binary file: {child}")
                        continue
                    if RE_SHEBANG.match(l):
                        files.append(child)
        elif child.is_dir():
            cfiles = _walk_dir(child)
            if cfiles:
                files.extend(cfiles)
    return files


###


def main() -> None:
    j = json.loads(
        "\n".join(l for l in DEVC_JSON.read_text().split("\n") if not re.match(r"^\s*//", l))
    )
    shellcheck_params: list[str] = j["settings"]["shellcheck.customArgs"]
    shfmt_params: list[str] = j["settings"]["shellformat.flag"].split()
    if "-d" not in shfmt_params:
        shfmt_params.append("-d")
    scripts = find_scripts()

    shellcheck = Linter(LinterType.shellcheck, shellcheck_params)
    shfmt = Linter(LinterType.shfmt, shfmt_params)
    linters = [shellcheck, shfmt]

    errs: list[LintError] = []
    for linter in linters:
        for spath in scripts:
            log(f"linting {spath.relative_to(REPO_ROOT)} with {linter.name}")
            lint_err = linter.run(spath)
            if lint_err:
                err(f"{spath.name} failed {linter.name}")
                errs.append(lint_err)

    if errs:
        err(f"Linting finished with {len(errs)} errors in {len(set([e.file for e in errs]))} files")
        for e in errs:
            print(f"{e.file}:")
            print(f"{e.linter.name} return code: {e.rc}")
            print(e.log)
            print()
        exit(1)
    else:
        log(f"Linting passed on {len(scripts)} files")


###

if __name__ == "__main__":
    main()
