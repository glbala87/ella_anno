#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

import click

###

ANNO_LABEL_BASE = "io.ousamg.anno"

DEFINITION_TEMPLATE = """
Bootstrap: docker
From: {source_image}

%labels
    {labels}
"""

###


def err(msg: str) -> None:
    print(msg, file=sys.stderr)


def get_labels(source_image: str) -> str:
    resp = subprocess.run(
        ["docker", "inspect", source_image],
        capture_output=True,
    )
    if resp.returncode != 0:
        raise RuntimeError(f"Failed to inspect docker image {source_image}: {resp.stderr.decode()}")
    image_metadata = json.loads(resp.stdout.decode())[0]
    labels = image_metadata["Config"]["Labels"].copy()
    labels[f"{ANNO_LABEL_BASE}.docker.name"] = image_metadata["RepoTags"][0]
    labels[f"{ANNO_LABEL_BASE}.docker.digest"] = image_metadata["RepoDigests"][0]
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
    type=click.Path(dir_okay=False, writable=True),
    default=(Path(__file__).resolve().parents[1] / "Singularity").relative_to(Path.cwd()),
    show_default=True,
    help="Singularity definition file name",
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
    force: bool,
) -> None:
    output_path = Path(output_file)
    if output_path.exists() and not force:
        raise FileExistsError(
            f"{output_path} already exists. Remove it or use --force to overwrite"
        )

    format_opts = {
        "source_image": source_image,
        "labels": get_labels(source_image),
    }
    if format_opts["labels"] is None:
        err(f"No labels to import, just build directly from the docker image")
        exit(1)

    def_content = DEFINITION_TEMPLATE.format(**format_opts)
    output_path.write_text(def_content.strip() + "\n")

    print(f"{output_path.resolve().relative_to(Path.cwd())} - {source_image}")


###

if __name__ == "__main__":
    main()
