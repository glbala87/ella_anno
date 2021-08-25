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

###


def find_root() -> Path:
    this_dir = Path(__file__).resolve().parent
    for p in [this_dir, *this_dir.parents]:
        git_cfg = p / ".git" / "config"
        if git_cfg.exists() and git_cfg.is_file():
            return p
    raise FileNotFoundError(f"Unable to locate repo root starting from {this_dir}")


IGNORE_DIRS = [".venv", ".git", "release", "build", "scratch", "thirdparty"]
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
                str(file),
                cmd,
                res.stdout.strip(),
            )
        return None


@dataclass
class LinterSettings:
    shfmt: list[str]
    shellcheck: list[str]


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


def find_scripts(dir_name: Path) -> Sequence[Path]:
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
                        logger.debug(f"skipping binary file: {child}")
                        continue
                    if RE_SHEBANG.match(l):
                        files.append(child)
        elif child.is_dir() and child.name not in IGNORE_DIRS:
            cfiles = find_scripts(child)
            if cfiles:
                files.extend(cfiles)
    return files


def load_settings(file: Path, strict: bool = False) -> LinterSettings:
    if not file.exists() or not file.is_file():
        msg = f"{file} does not exist, cannot load linter settings"
        if strict:
            raise FileNotFoundError(msg)
        else:
            logger.warning(f"{msg}. Continuing with default settings...")

    defaults: dict[str, list[str]] = {k: [] for k in LinterSettings.__annotations__}
    obj = LinterSettings(**defaults)
    cfg = json.loads(
        "\n".join(l for l in file.read_text().split("\n") if not re.match(r"^\s*//", l))
    )
    # most shellcheck settings should be stored in .shellcheckrc
    obj.shellcheck = cfg["settings"].get("shellcheck.customArgs", [])
    obj.shfmt = cfg["settings"].get("shellformat.flag", "").split()

    if "-d" not in obj.shfmt:
        # -d prints diffs and returns non-zero
        # -l lists filenames that need formatting, but still exits 0
        obj.shfmt.append("-d")

    return obj


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
    if not any([use_shellcheck, use_shfmt]):
        raise click.UsageError(f"At least one linter must be enabled")

    set_logs(verbose)
    repo_root = find_root()
    devc_json = repo_root / ".devcontainer" / "devcontainer.json"
    params = load_settings(devc_json)

    linters: list[Linter] = []
    if use_shellcheck:
        linters.append(Linter(LinterType.shellcheck, params.shellcheck))

    if use_shfmt:
        linters.append(Linter(LinterType.shfmt, params.shfmt))
    logger.info(f"Using linters: {', '.join(l.name for l in linters)}")

    scripts = find_scripts(repo_root)
    if dry_run:
        print(f"Found {len(scripts)} files:")
        for s in scripts:
            print(s)
        print()

    errs: list[LintError] = []
    for linter in linters:
        if dry_run:
            cmd_str = " ".join(linter.cmd("$filename"))
            print(f"{linter.name}: {cmd_str}")
            continue

        for spath in scripts:
            if verbose:
                logger.info(f"linting {spath.relative_to(repo_root)} with {linter.name}")
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
