#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from urllib.error import HTTPError
from base64 import b64encode
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import requests
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


def err(msg: str) -> None:
    print(msg, file=sys.stderr)


# scope ref: https://docs.docker.com/registry/spec/auth/scope/
def gen_jwt_token(username: str, auth_token: str, repo: str) -> str:
    encoded_auth = b64encode(f"{username}:{auth_token}".encode()).decode()
    resp = requests.get(
        url=f"https://gitlab.com/jwt/auth?service=container_registry&scope=repository:{repo}:pull",
        headers={f"Authorization": f"basic {encoded_auth}"},
    )
    body = parse_resp(resp)
    return body["token"]


def get_local_metadata(source_image: str) -> dict[str, Any]:
    resp = subprocess.run(
        ["docker", "inspect", source_image],
        capture_output=True,
    )
    if resp.returncode != 0:
        raise RuntimeError(f"Failed to inspect docker image {source_image}: {resp.stderr.decode()}")
    return json.loads(resp.stdout.decode())[0]


def parse_resp(resp: requests.Response) -> dict[str, Any]:
    if resp.status_code != 200:
        err(f"Got {resp.status_code} attempting to fetch {resp.request.url}")
        if resp.status_code in (401, 403):
            if resp.request.headers.get("Authorization") is None:
                err(f"No authorization header on request")
            www_auth: Optional[str] = resp.headers.get("www-authenticate")
            if www_auth is None:
                err(
                    f"Got {resp.status_code} fetching {resp.request.url}, but no info in www-authenticate"
                )
            else:
                auth_details = {
                    parts[0]: parts[1].strip('"')
                    for f in www_auth.split(",")
                    if (parts := f.split("=", 1))
                }
                if auth_details.get("scope"):
                    e = RuntimeError(
                        f"JWT token has insufficient scope, needs {auth_details['scope']}"
                    )
                    raise e
        print("error headers:")
        for k, v in resp.headers.items():
            print(f"{k}: {v}")
        print(f"\nreason: {resp.text}")
        breakpoint()
    return resp.json()


def get_registry_labels(source_image: str) -> dict[str, Any]:
    try:
        gitlab_user = os.environ["GITLAB_USER"]
        gitlab_token = os.environ["GITLAB_TOKEN"]
    except KeyError as e:
        print(e)
        raise EnvironmentError(
            f"You must have GITLAB_USER and GITLAB_TOKEN available in your environment to access the container registry"
        )

    registry_base = "registry.gitlab.com"
    base_url = f"https://{registry_base}/v2"
    repo, tag = source_image.replace(f"{registry_base}/", "").split(":")

    registry_token = gen_jwt_token(gitlab_user, gitlab_token, repo)
    default_headers = {"Authorization": f"Bearer {registry_token}"}
    digest_resp = parse_resp(
        requests.get(
            f"{base_url}/{repo}/manifests/{tag}",
            headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"}.update(
                default_headers
            ),
        )
    )
    config_digest = digest_resp["config"]["digest"]

    config_resp = parse_resp(
        requests.get(
            f"https://registry.gitlab.com/v2/{repo}/blobs/{config_digest}",
            headers=default_headers,
        )
    )
    breakpoint()
    return config_resp["container_config"]["Labels"]


def get_labels(source_image: str, root_label: str, is_local: bool = True) -> Optional[str]:
    if is_local:
        image_metadata = get_local_metadata(source_image)
    else:
        image_metadata = get_registry_labels(source_image)

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
        "labels": get_labels(source_image, root_label, use_local),
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
