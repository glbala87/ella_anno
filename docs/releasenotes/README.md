---
title: Latest release
---

# Release notes: Latest releases

|Major versions|Minor versions|
|:--|:--|
[v2.2](#version-2-2)|[v2.2.1](#version-2-2-1), [v2.2.1a](#version-2-2-1a)
[v2.1](#version-2-1)|[v2.1.1](#version-2-1-1), [v2.1.2](#version-2-1-2)
[v2.0](#version-2-0)|[v2.0.1](#version-2-0-1), [v2.0.2](#version-2-0-2), [v2.0.3](#version-2-0-3)

<!-- See [older releases](/releasenotes/olderreleases.md) for earlier versions.-->

## Version 2.2.2

Release date: 23.02.2021

<!-- MR !53, !56 -->
- Minor improvements to backend.
<!-- MR !57 -->
- Updated ClinVar to version 20210222.

## Version 2.2.1a

Release date: 17.12.2020

<!-- MR !50 -->
- Updated ClinVar to version 20201203.

## Version 2.2.1

Release date: 15.12.2020

<!-- MR !52 -->
- Fixed bug where VCFs with ALT variants with missing variants were erroneously set to `.`.

## Version 2.2

Release date: 10.12.2020

<!-- MR !43 -->
- Moved all code to Python 3.
<!-- MR !51 -->
- Non-default ports are now allowed for Postgres.
<!-- MR !49 -->
- Updated UTA to version 20201027 (moved to DigitalOcean and part of `datasets.json`).

## Version 2.1.2

Release date: 24.11.2020

<!-- MR !47 -->
- Removed link to sliced vcf.
<!-- MR !46 -->
- Added proper handling of GATK star alleles (add code to remove star alleles that are conflicting with downstream tools).
<!-- MR !48 -->
- Fixed issue with PYTHONPATH in Python 3.
<!-- MR !45 -->

## Version 2.1.1

Release date: 16.11.2020

<!-- MR !45 -->
- Fixed issue with slicing of multiallelic blocks.

## Version 2.1

Release date: 23.09.2020

<!-- MR !42 -->
- Fixed pyrsistent version to 0.15.7 (Python 2 compatible).
<!-- MR !38 -->
- Moved vt decompose and vt normalize before slicing, to avoid slicing on non-normalized data.
<!-- MR !41 -->
- Allowed ANNOBUILDER_IMAGE_NAME to be specified.
<!-- MR !37 -->
- Added CI-test to check datasets.json against DigitalOcean.
<!-- MR !36 -->
- Fixed remaining issues with duplicates in `vcfanno_config.toml`.
<!-- MR !34 -->
- Added license
<!-- MR !35, !40 -->
- Updated ClinVar to version 20200907.
<!-- No release notes: MR !39: Add data MR template -->

## Version 2.0.3

Release date: 13.07.2020

<!-- MR !30 -->
- Fixed issue with duplicates in `vcfanno_config.toml`.
<!-- MR !31 -->
- Added possibility to override envs in Makefile.
- Added caching for Singularity.
<!-- MR !32 -->
- Updated ClinVar to version 20200626.

## Version 2.0.2

Release date: 18.05.2020

<!-- MR !28 -->
- Updated ClinVar to version 20200514.

## Version 2.0.1

Release date: 13.05.2020

<!-- MR !25 -->
- Added option to set VEP buffer size in `annotate.sh` and environment variable.

## Version 2.0

Release date: 13.05.2020

- Initial public release.


