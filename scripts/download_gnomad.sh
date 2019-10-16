#!/bin/bash -e

# download gnomAD from http://gnomad.broadinstitute.org/downloads
#
# gnomAD keeps changing file name formats. This version is configured for the 2.0.2 release

usage() {
    if [[ ! -z $1 ]]; then
        echo "$1"
    fi
    echo
    echo USAGE:
    echo "    $0 -r GNOMAD_REVISION"
    echo
    exit 1
}

while [ $# -gt 1 ]; do
  key="$1"
  case "$key" in
    -r|--revision)
      REVISION="$2"
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

if [ -z "$REVISION" ]
then
  usage "Error! revision is missing, e.g. 2.0.2"
fi

GSUTIL=$(which gsutil 2>/dev/null)

if [[ -z $GSUTIL ]]; then
    usage "Unable to find gsutil, make sure it is installed, in PATH and try again"
fi

# Download exome data
$GSUTIL cp gs://gnomad-public/release/${REVISION}/vcf/exomes/gnomad.exomes.r${REVISION}.sites.vcf.bgz* .
# Download genome data
$GSUTIL cp gs://gnomad-public/release/${REVISION}/vcf/genomes/gnomad.genomes.r${REVISION}.sites.chr*.vcf.bgz* .
