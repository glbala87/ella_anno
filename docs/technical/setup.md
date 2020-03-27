---
title: Setup
---

# Setup

::: warning NOTE
This documentation is a work in progress and is incomplete.

Please contact developers for more details.
:::

This page describes the setup process of ELLA anno.

[[toc]]

## Requirements

-   [Docker](https://docs.docker.com/install/)
-   make (`apt install make`, `yum install make`, `apk add make`, _etc._)

### Optional requirements

-   [Singularity](https://github.com/sylabs/singularity)
-   [Buildkit](https://github.com/moby/buildkit)
-   [Supervisor](https://github.com/Supervisor/supervisor)

## Installation

ELLA anno is available in both Docker and Singularity containers. It can also be set up to be used locally, but a container is recommended. We also recommend using [buildkit](https://github.com/moby/buildkit) for faster docker builds. You may see a warning about unconsumed arguments if you build the docker images without buildkit installed/enabled, but it doesn't negatively impact the images in any way.

Installation process: 

1. Clone the repo
    - `git clone git@gitlab.com:alleles/ella-anno`
2. Check out the desired release
    - `git checkout v2.0.0`
3. Build the docker images
    - `make build`
    - `make build-annobuilder`
4. Download the annotation datasets
    - `make download-data`
5. Generate singularity images (if desired)
    - `make singularity-build`

## Running ELLA anno

Start the container:
- _Docker:_ `make anno`
- _Singularity:_ `make singularity-start`

## Annotate options

Options in `/src/annotation/annotate.sh`

Option	|	Explanation
:---	|	:---
`--vcf [vcf]` | Input VCF
`--hgvsc [hgvsc]` | Input HGVSC
`--regions [regions]` | Regions to slice input on
`--convert` | Flag to run conversion only, not annotation
`-o`/`--outfolder [outfolder]` | Output folder (default: working directory)
`-p`/`--processes` | Number of cores to use for time-consuming annotation steps (default number of cores available)
