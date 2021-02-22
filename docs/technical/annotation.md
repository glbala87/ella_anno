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

## Annotation tool: VEP

ELLA anno uses Ensembl's [Variant Effect Predictor (VEP)](https://www.ensembl.org/info/docs/tools/vep/index.html) for annotation. Settings are managed in `/src/annotation/annotate.sh`. 

## Data sources 

### Datasets used by anno

|Type | Name | Source | Note|
|:--|:--|:--|:--|
Genome | Human genome GRCh37 | [GATK Resource Bundle](https://gatk.broadinstitute.org/hc/en-us/articles/360035890811-Resource-bundle) | ELLA currently requires the GRCh37 build of the human genome, and **does not** support GRCh38.
Genes | HGNC | [HGNC](https://www.genenames.org) | Gene ID is fetched from either NCBI gene ID, Ensembl gene ID or gene symbol.
Genes | RefGene | [UCSC](http://hgdownload.soe.ucsc.edu/goldenPath/hg19/database/) | Used for slicing of gnomAD data.
Transcripts | RefSeq (GFF) | [NCBI](ftp://ftp.ncbi.nlm.nih.gov/refseq/H_sapiens/annotation/GRCh37_latest/refseq_identifiers/GRCh37_latest_genomic.gff.gz) | 
Transcripts | RefSeq (interim) | [NCBI](ftp://ftp.ncbi.nlm.nih.gov/genomes/Homo_sapiens/ARCHIVE/ANNOTATION_RELEASE.109/GRCh37.p13_interim_annotation/interim_GRCh37.p13_top_level_2017-01-13.gff3.gz) | See [Golden Helix blog](https://blog.goldenhelix.com/updating-varseqs-transcript-annotation-along-with-ncbi-refseq-genes-interim-release/).
Transcripts | Universal Transcript Archive (UTA) | [Biocommons](https://github.com/biocommons/uta/) |
Transcripts | SeqRepo | [Biocommons](https://github.com/biocommons/biocommons.seqrepo) | 
Population frequencies | Genome Aggregation Database (gnomAD) | [Broad Institute](https://gnomad.broadinstitute.org/) | Updating gnomAD might break a number of things the ELLA application, and should not be done without thorough testing. From v3.0, gnomAD is only available for genome build GRCh38, which is currently incompatible with ELLA.
Population frequencies | In-house database | | No in-house database is included with the service, this must be added in your own setup.
Mutation database | ClinVar | [NCBI](https://www.ncbi.nlm.nih.gov/clinvar/) | 
Mutation database | Human Gene Mutation Database | [Qiagen (Pro version)]((https://digitalinsights.qiagen.com/products-overview/clinical-insights-portfolio/human-gene-mutation-database/)) | Pro version requires a paid subscription, and the dataset is not included in `/ops/datasets.json` in the source code. An alternaive is to use the [free version](http://www.hgmd.cf.ac.uk/ac/index.php) (3 years outdated). 

### Dataset versions

Current versions of datasets used in the annotation service and scripts/commands for downloading or updating are specified in `/ops/datasets.json`.

### Custom annotation

If you have other data sources you wish to annotate with, you can easily extend the reference data sources by modifying `/ops/datasets.json` with your custom data sources. See also the [vcfanno documentation](https://github.com/brentp/vcfanno) for the vcfanno section of `datasets.json`.

See the (currently non-existent) `/examples` repo dir for examples on how to extend ELLA anno with your own data.

