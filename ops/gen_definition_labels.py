#!/usr/bin/env python3
import json
import subprocess
import sys
from enum import Enum
from pathlib import Path

import click

###


class Bootstrap(str, Enum):
    local = "docker-daemon"
    registry = "docker"
    default = registry

    def __str__(self) -> str:
        return self.value


###

DEFINITION_TEMPLATE = """
Bootstrap: {bootstrap}
From: {source_image}

%labels
    {labels}
""".lstrip()

###


def err(msg: str) -> None:
    print(msg, file=sys.stderr)


def get_labels(source_image: str, base_label: str) -> str:
    resp = subprocess.check_output(
        ["docker", "inspect", source_image],
    )
    image_metadata = json.loads(resp.decode())[0]

    if not image_metadata["Config"]:
        raise KeyError(f"missing Config key in docker inspect output: {image_metadata}")
    if image_metadata["Config"].get("Labels"):
        labels = image_metadata["Config"]["Labels"].copy()
    else:
        labels = {}

    if image_metadata.get("RepoTags"):
        labels[f"{base_label}.docker.name"] = image_metadata["RepoTags"][0]
    if image_metadata.get("RepoDigests"):
        labels[f"{base_label}.docker.digest"] = image_metadata["RepoDigests"][0]
    return "\n    ".join(f"{k} {v}" for k, v in labels.items())


###


@click.command(
    help="Generates a simple definition file to include Docker image labels in the final Singularity image",
)
@click.option(
    "--image-slug",
    "-i",
    "source_image",
    required=True,
    metavar="DOCKER_IMAGE:TAG",
    help="use a custom docker image slug",
)
@click.option(
    "--base-label",
    "-l",
    "base_label",
    required=True,
    help="reverse URI to use as the base for custom labels",
)
@click.option(
    "--output-file",
    "-o",
    type=click.Path(dir_okay=False, writable=True),
    default=(Path(__file__).resolve().parents[1] / "Singularity").relative_to(Path.cwd()),
    show_default=True,
    help="Singularity definition file name",
)
@click.option(
    "--bootstrap",
    "-b",
    type=click.UNPROCESSED,
    default=Bootstrap.default.name,
    metavar="|".join(b.name for b in Bootstrap),
    show_default=True,
    callback=lambda *x: Bootstrap[x[-1]],
    help="Use registry/docker or local/docker-daemon as bootstrap",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="overwrite any existing files",
)
def main(
    source_image: str,
    base_label: str,
    output_file: Path,
    bootstrap: Bootstrap,
    force: bool,
) -> None:
    output_path = Path(output_file)
    if output_path.exists() and not force:
        raise FileExistsError(
            f"{output_path} already exists. Remove it or use --force to overwrite"
        )

    format_opts = {
        "source_image": source_image,
        "labels": get_labels(source_image, base_label),
        "bootstrap": bootstrap,
    }
    if format_opts["labels"] is None:
        err(f"No labels to import, just build directly from the docker image")
        exit(1)

    output_path.write_text(DEFINITION_TEMPLATE.format(**format_opts))
    print(f"{output_path.resolve().relative_to(Path.cwd())} - {source_image}")


###

if __name__ == "__main__":
    main()
