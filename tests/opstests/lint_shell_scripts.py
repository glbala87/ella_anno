#!/usr/bin/env python3

import click
import json
import logging
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from shlex import quote
from typing import Optional, Union

logger = logging.getLogger()
log_template = "%(asctime)s - %(name)s - %(levelname)-7s - %(message)s"
log_format = logging.Formatter(log_template)

REPO_ROOT = Path(__file__).parents[2]
CHECK_DIRS = ["bin", "ops", "scripts", "src", "tests"]
CHECK_PATHS = [REPO_ROOT / d for d in CHECK_DIRS]
DEVC_JSON = REPO_ROOT / ".devcontainer" / "devcontainer.json"
IGNORE_NAMES = ["MD5SUM", "DATA_READY"]
INCLUDE_SUFFIX = [".sh", ""]
RE_SHEBANG = re.compile(r"^#!(?:/bin/|/usr/bin/env )(?:ba)sh\b")

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

    def cmd(self, file: Union[Path, str]) -> list[str]:
        return [quote(c) for c in [str(self.path), *self.params, str(file)]]

    @property
    def name(self) -> str:
        return self._type.name

    def run(self, file: Path) -> Optional[LintError]:
        # use shlex.quote to prevent shell injection
        cmd = self.cmd(file)
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


def set_logs(verbose: bool = False):
    if verbose:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING
    logger.setLevel(log_level)
    if logger.handlers:
        console = logger.handlers[0]
    else:
        console = logging.StreamHandler()
        logger.addHandler(console)
    console.setFormatter(log_format)

    # TODO: enable detailed logging to file as CI artifact maybe?
    # log_file = "linter.log"
    # file_handler = logging.FileHandler(log_file, encoding="utf-8")
    # file_handler.setLevel(log_level)
    # file_handler.setFormatter(log_format)
    # logger.addHandler(file_handler)


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
                        logger.info(f"skipping binary file: {child}")
                        continue
                    if RE_SHEBANG.match(l):
                        files.append(child)
        elif child.is_dir():
            cfiles = _walk_dir(child)
            if cfiles:
                files.extend(cfiles)
    return files


###


@click.command(
    help="Finds shell scripts and runs shellcheck and shfmt on them. Both are used by default, but either can be disabled."
)
@click.option("--no-shellcheck", "use_shellcheck", is_flag=True, default=True)
@click.option("--no-shfmt", "use_shfmt", is_flag=True, default=True)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="prints a list of scripts and commands without running them",
)
@click.option("--exit-fast", "-x", is_flag=True, help="exit on first lint failure")
@click.option("--verbose", "-v", is_flag=True, help="print detailed lint info")
def main(
    use_shellcheck: bool, use_shfmt: bool, dry_run: bool, exit_fast: bool, verbose: bool
) -> None:
    set_logs(verbose)
    if not any([use_shellcheck, use_shfmt]):
        raise click.UsageError(f"At least one linter must be enabled")
    j = json.loads(
        "\n".join(l for l in DEVC_JSON.read_text().split("\n") if not re.match(r"^\s*//", l))
    )
    scripts = find_scripts()
    if dry_run:
        print(f"Found {len(scripts)} files:")
        for s in scripts:
            print(s)
        print()

    linters: list[Linter] = []
    if use_shellcheck:
        # most should be stored in .shellcheckrc, but include these anyway
        shellcheck_params: list[str] = j["settings"]["shellcheck.customArgs"]
        linters.append(Linter(LinterType.shellcheck, shellcheck_params))

    if use_shfmt:
        shfmt_params: list[str] = j["settings"]["shellformat.flag"].split()
        if "-d" not in shfmt_params:
            # -d prints diffs and returns non-zero
            # -l lists filenames that need formatting, but still exits 0
            shfmt_params.append("-d")
        linters.append(Linter(LinterType.shfmt, shfmt_params))

    errs: list[LintError] = []
    for linter in linters:
        if dry_run:
            cmd_str = " ".join(linter.cmd("$filename"))
            print(f"{linter.name}: {cmd_str}")
            continue
        for spath in scripts:
            if verbose:
                logger.info(f"linting {spath.relative_to(REPO_ROOT)} with {linter.name}")
            lint_err = linter.run(spath)
            if lint_err:
                if verbose or exit_fast:
                    logger.error(f"{spath.name} failed {linter.name}")

                if exit_fast:
                    if verbose:
                        print(lint_err.log)
                    logger.error(f"Additional linting aborted")
                    exit(1)

                errs.append(lint_err)

    if errs:
        logger.error(
            f"Linting finished with {len(errs)} errors in {len(set([e.file for e in errs]))} files"
        )
        for e in errs:
            print(f"{e.file}: failed {e.linter.name}")
            if verbose:
                print(f"return code: {e.rc}")
                print(e.log)
        exit(1)
    elif not dry_run:
        logger.info(f"Linting passed on {len(scripts)} files")


###

if __name__ == "__main__":
    main()
