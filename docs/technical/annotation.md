---
Title: Annotation
---

# Annotation

::: warning NOTE
This documentation is a work in progress and is incomplete.

Please contact developers for more details.
:::

This page describes the default annotation sources included with the service and how to add additional annotation sources.

[[toc]]

## General annotation

### VEP

Source: [Ensembl Variant Effect Predictor (VEP)](https://www.ensembl.org/info/docs/tools/vep/index.html)
Version: 98.3

#### VEP settings used in the annotation service

See `/src/annotation/annotate.sh`

#### Update

Updating VEP might break a number of things the ELLA application, and should not be done without thorough testing.

### Genes

Source: [HGNC](https://www.genenames.org) (ID fetched from either NCBI gene ID, Ensembl gene ID or gene symbol)
Version: 

### Transcripts

Source: RefSeq GFF files (added to VEP)

## Population frequencies

### GnomAD

Source: [Genome Aggregation Database (gnomAD)](https://gnomad.broadinstitute.org/)
Version: 2.0

#### Update

Updating gnomAD might break a number of things the ELLA application, and should not be done without thorough testing. From v3.0, gnomAD is only available for genome build GRCh38, which is currently incompatible with ELLA anno.

### In-house database

No in-house database is included with the service. To add your own database, you need to ...

## External mutation databases

### ClinVar

Source: [ClinVar](https://www.ncbi.nlm.nih.gov/clinvar/)

#### Update

Updates should be done monthly, timed with ClinVar's releases. To update, run ...
 
### HGMD (Pro)

Source: Need [pro subscription](https://digitalinsights.qiagen.com/products-overview/clinical-insights-portfolio/human-gene-mutation-database/), or use [free version](http://www.hgmd.cf.ac.uk/ac/index.php) (3 years outdated).

#### Update

Updates should be done quarterly, timed with HGMD's releases. To updated, run ...

## Custom annotation

If you have other data sources you wish to annotate with, you can easily extend the reference data sources by modifying `/ops/datasets.json` with your custom data sources. See also the [vcfanno documentation](https://github.com/brentp/vcfanno) for the vcfanno section of `datasets.json`.

See the (currently non-existent) `/examples` repo dir for examples on how to extend ELLA anno with your own data.

