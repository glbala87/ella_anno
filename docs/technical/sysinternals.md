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

VEP

### Genes and transcripts

VEP with added RefSeq GFF files, HGNC.

- Uses [downloaded HGNC data sources](https://www.genenames.org) for fetching HGNC ID from either NCBI gene ID, Ensembl gene ID or gene symbol.
- On deposit, RefSeq sources are prioritized per variant as follows: 1. latest GFF, 2. interim GFF, 3. VEP default. Lower priority sources are discarded.
- Chooses transcript that matches genepanel transcript if available, otherwise, chooses latest available version.


## Conversion of manual import data

Converts manual import data from ELLA's [import module](http://allel.es/docs/manual/data-import-reanalyses.html#import-variant-data).

Uses [hgvs](https://github.com/biocommons/hgvs) and [uta](https://github.com/biocommons/uta) modules from [biocommons](https://github.com/biocommons).

## Extract PubMed IDs

From ClinVar and HGMD (note licence requirement).

## Allele check

Variant REF allele against genome REF.


