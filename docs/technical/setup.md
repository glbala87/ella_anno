---
title: Setup
---

# Setup

::: warning NOTE
This documentation is a work in progress and is incomplete.

Please contact developers for more details.
:::

Setup of ELLA anno ...

## Annotate options

Options in annotate.sh

Option	|	Explanation
:---	|	:---
--vcf [vcf] | Input VCF
--hgvsc	[hgvsc] | Input HGVSC
--regions [regions] | Regions to slice input on
--convert | Flag to run conversion only, not annotation
-o/--outfolder [outfolder] | Output folder (default: working directory)
-p/--processes | Number of cores to use for time-consuming annotation steps (default number of cores available)