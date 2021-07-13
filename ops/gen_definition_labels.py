#!/usr/bin/env python3
import json
import subprocess
import sys
from enum import Enum
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Optional

import click

###

OCI_LABEL_BASE = "org.opencontainers.image"
ANNO_LABEL_BASE = "io.ousamg.anno"


class Bootstrap(str, Enum):
    registry = "docker"
    local = "docker-daemon"


DEFINITION_TEMPLATE = """
Bootstrap: {bootstrap}
From: {source_image}

%labels
    {labels}
"""

###


def get_labels(source_image: str, root_label: str) -> Optional[str]:
    resp = subprocess.run(
        ["docker", "inspect", source_image],
        capture_output=True,
    )
    if resp.returncode != 0:
        raise RuntimeError(f"Failed to inspect docker image {source_image}: {resp.stderr.decode()}")
    image_metadata = json.loads(resp.stdout.decode())[0]

    labels = image_metadata["Config"]["Labels"].copy()
    labels[f"{root_label}.docker.name"] = image_metadata["RepoTags"][0]
    labels[f"{root_label}.docker.digest"] = image_metadata["RepoDigests"][0]

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
    "--output-file",
    "-o",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),  # type: ignore
    default=(Path(__file__).parents[1] / "Singularity").relative_to(Path.cwd()),
    show_default=True,
    help="Singularity definition file name",
)
@click.option(
    "--root-label",
    default=ANNO_LABEL_BASE,
    show_default=True,
    envvar="DEF_ROOT_LABEL",
    help="Root domain used with custom labels",
)
@click.option(
    "--local",
    "use_local",
    is_flag=True,
    default=False,
    help="use locally built docker images instead of from a remote registry",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="overwrite any existing files",
)
def main(
    source_image: str,
    output_file: Path,
    root_label: str,
    use_local: bool,
    force: bool,
) -> None:
    if output_file.exists() and not force:
        raise FileExistsError(
            f"{output_file} already exists. Remove it or use --force to overwrite"
        )

    format_opts = {
        "bootstrap": Bootstrap.local.value if use_local else Bootstrap.registry.value,
        "source_image": source_image,
        "labels": get_labels(source_image, root_label),
    }
    if format_opts["labels"] is None:
        print(f"No labels to import, just build directly from the docker image", file=sys.stderr)
        exit(1)

    def_content = DEFINITION_TEMPLATE.format(**format_opts)
    output_file.write_text(def_content.strip() + "\n")

    print(f"{output_file.resolve().relative_to(Path.cwd())} - {source_image}")


###

if __name__ == "__main__":
    main()
