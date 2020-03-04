---
title: System internals
---

# System internals

::: warning NOTE
This documentation is a work in progress and is incomplete.

Please contact developers for more details.
:::

Detailed description of the annotation service ...

## Annotation

VEP ...

### Genes and transcripts

VEP with added RefSeq GFF files, HGNC.

- Uses [downloaded HGNC data sources](https://www.genenames.org) for fetching HGNC ID from either NCBI gene ID, Ensembl gene ID or gene symbol.
- On deposit, RefSeq sources are prioritized per variant as follows: 1. Latest GFF; 2. Interim GFF; 3. VEP default. Lower priority sources are discarded.
- Chooses the transcript version that matches the version specified in the genepanel if available, otherwise, chooses latest available version.


## Conversion of manual import data

Conversion of manual import data from ELLA's [import module](http://allel.es/docs/manual/data-import-reanalyses.html#import-variant-data) is handled using [hgvs](https://github.com/biocommons/hgvs) and [uta](https://github.com/biocommons/uta) modules from [biocommons](https://github.com/biocommons).

## Extract PubMed IDs

PubMed IDs for each variant are extracted from ClinVar, as well as HGMD if it has been added.

## Allele check

Each variant REF allele is checked against the genome REF allele. If there is a mismatch, ...


