#!/bin/bash

# gnomAD exomes is downloaded as one single file with all chromosomes
# parallel per chromosome processing due to large memory required by vt-rminfo
#  remove histogram fields and VEP annotation (CSQ field)
#  decomepose and normalize by vt
# merge by appending instead of vt-concatenate due to large memory required
# bgzip
# tabix

# get path to vcpipe-bin
# get gnomAD revision

set -eu -o pipefail

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BIN_DIR="$(basename $THIS_DIR)/bin"
DATA_DIR="$(basename $THIS_DIR)/data"
FASTA_DIR=$DATA_DIR/FASTA
GNOMAD_DATA_DIR=$DATA_DIR/variantDBs/gnomAD
GNOMAD_RAW_DIR=$GNOMAD_DATA_DIR/raw

usage() {
    if [[ ! -z $1 ]]; then
        echo "$1"
    fi
    echo
    echo "Usage:"
    echo "    $0 -f ~/path/to/human_g1k_v37_decoy.fasta -r 2.0.2"
    echo
    exit 1
}

log() {
    echo "[$$] $(date +%Y-%m-%d\ %H:%M:%S) - $1"
}

bail() {
    echo "$1"
    exit 1
}

pcnt() {
    CNT=$(pgrep -P $$ | wc -l)
    echo $((CNT - 1))
}

normalize_chrom() {
    chrom="$1"
    input_file="$2"
    output_file="$3"
    "$TABIX" -p vcf -h "$input_file" "$chrom" \
        | "$VT" rminfo - -t GQ_HIST_ALT,DP_HIST_ALT,AB_HIST_ALT,GQ_HIST_ALL,DP_HIST_ALL,AB_HIST_ALL,CSQ \
        | "$VT" decompose -s - \
        | "$VT" normalize -r "${REFERENCE}" -n - \
        > "$output_file"
}

while [ $# -gt 1 ]; do
    key="$1"
    case "$key" in
        -r|--gnomad-revision)
            GNOMADVERSION="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            break
            ;;
    esac
done

REFERENCE=$FASTA_DIR/human_g1k_v37_decoy.fasta.gz
if [[ ! -f "$REFERENCE" ]]; then
    usage "Error! Unable to find reference genome: '$REFERENCE', check it was synced correctly"
fi

if [ -z "$GNOMADVERSION" ]; then
    usage "Error! gnomAD revision missing."
fi

if [[ -f "$BIN_DIR/tabix" ]]; then
    TABIX="$BIN_DIR/tabix"
else
    bail "Unable to find tabix in $BIN_DIR"
fi

if [[ -f "$BIN_DIR/vt" ]]; then
    VT="$BIN_DIR/vt"
else
    bail "Unable to find vt in $BIN_DIR"
fi

if [[ -f "$BIN_DIR/bgzip" ]]; then
    BGZIP=$"BIN_DIR/bgzip"
else
    bail "Unable to find bgzip in $BIN_DIR"
fi

MAX_PCNT=${MAX_PCNT:-$(grep -c processor /proc/cpuinfo)}
EXOME_INPUT="$GNOMAD_RAW_DIR/gnomad.exomes.r${GNOMADVERSION}.sites.vcf.bgz"
EXOME_OUTPUT="$GNOMAD_DATA_DIR/gnomad.exomes.r${GNOMADVERSION}.norm.vcf"
declare -a EXOME_BY_CHR
# processing each chromosome in parallel due to large memory usage and long time taken by vt
for i in {1..22} X Y; do
    # don't kill CPU with too many jobs
    while [[ $(pcnt) -ge $MAX_PCNT ]]; do
        sleep 15
    done

    norm_fn="$GNOMAD_RAW_DIR/gnomad.exomes.r${GNOMADVERSION}.chr${i}.norm.vcf"
    EXOME_BY_CHR+=(norm_fn)
    normalize_chrom $i $EXOME_INPUT $norm_fn &
done
wait

# merge by appending instead of vt-concatenate due to large memory required by vt-concatenate
mkdir -p $GNOMAD_DATA_DIR
for input_chr in "${EXOME_BY_CHR[@]}"; do
    if [[ ! -e $EXOME_OUTPUT ]]; then
        cp $input_chr $EXOME_OUTPUT
    else
        "$VT" view $input_chr >> $EXOME_OUTPUT
    fi
done

#bgzip
$BGZIP "$EXOME_OUTPUT"

#index
$TABIX -p vcf "${EXOME_OUTPUT}.bgz"

# cleanup only after everything has succeeded
rm -rf $GNOMAD_RAW_DIR
