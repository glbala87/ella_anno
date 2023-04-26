---
title: Latest release
---

# Release notes: Latest releases

|Major versions|Minor versions|
|:--|:--|
[v2.7](#version-2-7-0)| [v2.7.0](#version-2-7-0), [v2.7.0a](#version-2-7-0a)
[v2.6](#version-2-6-0)| [v2.6.0](#version-2-6-0), [v2.6.0a](#version-2-6-0a), [v2.6.0b](#version-2-6-0b), [v2.6.0c](#version-2-6-0c), [v2.6.0d](#version-2-6-0d), [v2.6.0e](#version-2-6-0e), [v2.6.0f](#version-2-6-0f), [v2.6.0g](#version-2-6-0g)
[v2.5](#version-2-5-0)| [v2.5.0](#version-2-5-0)
[v2.4](#version-2-4-0)| [v2.4.1](#version-2-4-1)
[v2.3](#version-2-3-0)| [v2.3.1](#version-2-3-1), [v2.3.2](#version-2-3-2)
[v2.2](#version-2-2)|[v2.2.1](#version-2-2-1), [v2.2.1a](#version-2-2-1a), [v2.2.2](#version-2-2-2), [v2.2.3](#version-2-2-3), [v2.2.4](#version-2-2-4)
[v2.1](#version-2-1)|[v2.1.1](#version-2-1-1), [v2.1.2](#version-2-1-2)
[v2.0](#version-2-0)|[v2.0.1](#version-2-0-1), [v2.0.2](#version-2-0-2), [v2.0.3](#version-2-0-3)

<!-- See [older releases](/releasenotes/olderreleases.md) for earlier versions.-->

## Version 2.7.0a

Release date: 27.04.2023

#### Codebase
<!-- MR !127 -->
- release history documentation update

#### Data sources
<!-- MR !127 -->
- Updated Clinvar to version 20230406

## Version 2.7.0

Release date: 23.03.2023

#### Codebase

<!-- MR !125 -->
- Errors in configuration parsing are hard to trace
<!-- MR !118 -->
- Update VEP to 108.2
<!-- MR !123 -->
- Remove existing rawdata directories when sync_data.py called with --force

#### Data sources
<!-- MR !124 -->
- Updated Clinvar to version 20230302.

## Version 2.6.0g

Release date: 20.02.2023

#### Data sources
<!-- MR !121 -->
- Updated Clinvar to version 20230202.

## Version 2.6.0f

Release date: 24.01.2023

#### Codebase
<!-- MR !119 -->
- release history documentation update

#### Data sources
<!-- MR !119 -->
- Updated Clinvar to version 20230105.


## Version 2.6.0e

Release date: 30.12.2022

#### Codebase
<!-- MR !116 -->
- release history documentation update
- correct build command in docs

#### Data sources
<!-- MR !116 -->
- Updated Clinvar to version 20221201.

## Version 2.6.0d

Release date: 25.11.2022

#### Data sources
<!-- MR !114 -->
- Updated Clinvar to version 20221103.


## Version 2.6.0c

Release date: 18.10.2022

#### Data sources
<!-- MR !111 -->
- Updated Clinvar to version 20221006.

## Version 2.6.0b

Release date: 04.10.2022

#### Data sources
<!-- MR !109 -->
- Updated Clinvar to version 20220901.

## Version 2.6.0a

Release date: 18.08.2022

#### Data sources
<!-- MR !106 -->
- Updated Clinvar to version 20220804.

## >> Version 2.6

Release date: not released

#### Codebase
<!-- MR !102 -->
- Update the pipenv lock file

#### Data sources
<!-- MR !103 -->
- Updated Clinvar to version 20220707.

## >> Version 2.5

Release date: 20.06.2022

#### Codebase
<!-- MR !98 -->
- Show size of annotation data before downloading

#### Data sources
<!-- MR !99 -->
- Updated Clinvar to version 20220505.


## Version 2.4.1

Release date: 25.04.2022

#### Codebase
<!-- MR !94 -->
- release history documentation update

#### Data sources
<!-- MR !96 -->
- Updated Clinvar to version 20220407

## >> Version 2.4

Release date: 18.03.2022

#### Codebase
<!-- MR !89 -->
- generic anno config parser

#### Data sources
<!-- MR !92 -->
- Updated Clinvar to version 20220303.


## Version 2.3.2

Release date: 23.02.2022

#### Codebase
<!-- MR !86 -->
- Error log output is truncated in `ops/sync_data.py
<!-- MR !88 -->
- Trouble with permissions when indexing `FASTA` in container root folder


#### Data sources
<!-- MR !90 -->
- Updated Clinvar to version 20220203.


## Version 2.3.1

Release date: 12.02.2022

#### Codebase
<!-- MR !84 -->
- Use docker:// when USE_REGISTRY is set
<!-- MR !83 -->
- Various minor build fixes

#### Data sources
<!-- MR !78 -->
- Updated RefGene to version 20210928.
<!-- MR !82 -->
- Updated Clinvar to version 20220106.

## >> Version 2.3

Release date: 21.09.2021

#### Codebase
<!-- MR !68, !71 -->
- Moved to Pipenv/Pipfile for dependency management and updating packages. 
- Upgraded Python to v3.9.
- Upgraded PostgreSQL to version 13.
- Upgraded Docker base image to Debian 11 (Bullseye).
<!-- MR !70 (!71), !76, !77 -->
- Improvements to code base and dev environment.

#### Data sources
<!-- MR !62 -->
- Upgraded gnomAD to v2.1.1.
<!-- MR !64 -->
- Upgraded VEP to v104.3.
<!-- MR !63 -->
- Updated RefSeq to version 20201022.
<!-- MR !73 -->
- Removed miRNA from RefSeq data to mitigate [bug in VEP](https://github.com/Ensembl/ensembl-vep/issues/732#issuecomment-610938368).
<!-- MR !65 -->
- Upgraded biocommons seqrepo to version 2021-01-29.
<!-- MR !68 -->
- Updated UTA to version 20210129.
<!-- MR !72 -->
- Updated ClinVar to version 20210826.


## Version 2.2.4

Release date: 11.06.2021

#### Codebase
<!-- MR !67 -->
- Added force flag to get a clean data folder.

## Version 2.2.3

Release date: 10.06.2021

#### Codebase
<!-- MR !60 -->
- Anno now allows import of empty VCFs.

#### Data sources
<!-- MR !61 -->
- Updated ClinVar to version 20210529.

## Version 2.2.2

Release date: 23.02.2021

#### Codebase
<!-- MR !53, !56 -->
- Minor improvements to backend.

#### Data sources
<!-- MR !57 -->
- Updated ClinVar to version 20210222.

## Version 2.2.1a

Release date: 17.12.2020

#### Data sources
<!-- MR !50 -->
- Updated ClinVar to version 20201203.

## Version 2.2.1

Release date: 15.12.2020

#### Codebase
<!-- MR !52 -->
- Fixed bug where VCFs with ALT variants with missing variants were erroneously set to `.`.

## >> Version 2.2

Release date: 10.12.2020

#### Codebase
<!-- MR !43 -->
- Moved all code to Python 3.
<!-- MR !51 -->
- Non-default ports are now allowed for Postgres.

#### Data sources
<!-- MR !49 -->
- Updated UTA to version 20201027 (moved to DigitalOcean and part of `datasets.json`).

## Version 2.1.2

Release date: 24.11.2020

#### Codebase
<!-- MR !47 -->
- Removed link to sliced VCF.
<!-- MR !46 -->
- Added proper handling of GATK star alleles (add code to remove star alleles that are conflicting with downstream tools).
<!-- MR !48 -->
- Fixed issue with `PYTHONPATH` in Python 3.
<!-- MR !45 -->

## Version 2.1.1

Release date: 16.11.2020

#### Codebase
<!-- MR !45 -->
- Fixed issue with slicing of multiallelic blocks.

## >> Version 2.1

Release date: 23.09.2020

#### Codebase
<!-- MR !42 -->
- Fixed pyrsistent version to 0.15.7 (Python 2 compatible).
<!-- MR !38 -->
- Moved vt decompose and vt normalize before slicing, to avoid slicing on non-normalized data.
<!-- MR !41 -->
- Allowed `ANNOBUILDER_IMAGE_NAME` to be specified.
<!-- MR !37 -->
- Added CI-test to check `datasets.json` against DigitalOcean.
<!-- MR !36 -->
- Fixed remaining issues with duplicates in `vcfanno_config.toml`.
<!-- MR !34 -->
- Added license.

#### Data sources
<!-- MR !35, !40 -->
- Updated ClinVar to version 20200907.
<!-- No release notes: MR !39: Add data MR template -->

## Version 2.0.3

Release date: 13.07.2020

#### Codebase
<!-- MR !30 -->
- Fixed issue with duplicates in `vcfanno_config.toml`.
<!-- MR !31 -->
- Added possibility to override envs in Makefile.
- Added caching for Singularity.

#### Data sources
<!-- MR !32 -->
- Updated ClinVar to version 20200626.

## Version 2.0.2

Release date: 18.05.2020

#### Data sources
<!-- MR !28 -->
- Updated ClinVar to version 20200514.

## Version 2.0.1

Release date: 13.05.2020

#### Data sources
<!-- MR !25 -->
- Added option to set VEP buffer size in `annotate.sh` and environment variable.

## >> Version 2.0

Release date: 13.05.2020

- Initial public release.


