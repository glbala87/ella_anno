#!/bin/bash

# gnomAD exomes is downloaded as one single file with all chromosomes
# parallel per chromosome processing due to large memory required by vt-rminfo
#  remove histogram fields and VEP annotation (CSQ field)
#  decompose and normalize by vt
#  bgzip
#  tabix

set -e -o pipefail

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR=$(dirname "$(dirname $THIS_DIR)")
BIN_DIR=$ROOT_DIR/bin
DATA_DIR=$ROOT_DIR/data
FASTA_DIR=$DATA_DIR/FASTA
GNOMAD_DATA_DIR=$DATA_DIR/variantDBs/gnomAD
GNOMAD_RAW_DIR=$ROOT_DIR/rawdata/gnomAD

usage() {
    if [[ ! -z "$1" ]]; then
        echo "$1"
    fi
    echo
    echo "Usage:"
    echo "    $0 -v GNOMAD_VERSION [ -b /path/to/gene_regions.bed ]"
    echo
    echo "Options:"
    echo "  -v      gnomAD version. currently validated for 2.0.2"
    echo "  -b      path to bedfile of gene regions to slice genome data on (optional)"
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

syslog_min_time() {
    if [[ -z $1 ]]; then
        date +'%b %d %H'
    else
        date -d "$1" +'%b %d %H'
    fi
}

normalize_exome_chrom() {
    chrom="$1"
    input_file="$2"
    output_file="$3"
    "$TABIX" -p vcf -h "$input_file" $chrom \
        | perl -F'\t' -wlane 'if (substr($F[0], 0, 1) eq "#"){print join("\t", @F)}else{print join("\t", @F[0..6], join(";", (grep { ! /^(GQ_HIST_ALT|DP_HIST_ALT|AB_HIST_ALT|GQ_HIST_ALL|DP_HIST_ALL|AB_HIST_ALL|CSQ)=/ } (split ";", $F[7]))))}' \
        | "$VT" decompose -s - \
        | "$VT" normalize -r "${REFERENCE}" -n - \
        > "$output_file"
    log "Finished processing exome chromosome $chrom"
}

normalize_genome_chrom() {
    input_file="$1"
    output_file="$2"
    bed_opt="$3"
    "$TABIX" -h $bed_opt "$input_file" \
        | perl -F'\t' -wlane 'if (substr($F[0], 0, 1) eq "#"){print join("\t", @F)}else{print join("\t", @F[0..6], join(";", (grep { ! /^(GQ_HIST_ALT|DP_HIST_ALT|AB_HIST_ALT|GQ_HIST_ALL|DP_HIST_ALL|AB_HIST_ALL|CSQ)=/ } (split ";", $F[7]))))}' \
        | "$VT" decompose -s - \
        | "$VT" normalize -r "${REFERENCE}" -n - \
        > "$output_file"
    log "Finished processing genome file $input_file"
}

while getopts ":v:b:h" opt; do
    case "${opt}" in
        v)
            GNOMAD_VERSION="$OPTARG"
            ;;
        b)
            BED_REGIONS="$OPTARG"
            ;;
        h)
            usage
            ;;
        \?)
            usage "Invalid option: $OPTARG"
            ;;
        :)
            usage "Missing argument for $OPTARG"
            ;;
    esac
done

REFERENCE=$FASTA_DIR/human_g1k_v37_decoy.fasta.gz
if [[ ! -f "$REFERENCE" ]]; then
    usage "Error! Unable to find reference genome: '$REFERENCE', check it was synced correctly"
fi

if [[ -z "$GNOMAD_VERSION" ]]; then
    usage "Error! gnomAD version missing."
fi

if [[ -z "$BED_REGIONS" ]]; then
    echo "Warning: no bed file specified. Genomic output will be very large"
elif [[ ! -f "$BED_REGIONS" ]]; then
    usage "Error! Unable to find bed file: $BED_REGIONS"
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
    BGZIP="$BIN_DIR/bgzip"
else
    bail "Unable to find bgzip in $BIN_DIR"
fi

# memory intensive, can easily use 10GB per normalize_exome_chrom call
# Make sure swap is also enabled or can risk OOM killing by the kernel
# SWAP_ON=$(swapon --show | wc -l)
# if [[ $SWAP_ON -eq 0 ]]; then
#     echo " *** WARNING *** Swap does not appear to be enabled. Processes are likely to be killed by the kernel"
# fi
# MEM_MAX_PCNT=$(grep -P '(Mem|Swap)Total' /proc/meminfo | perl -lane 'if ($F[2] eq "kB"){$sum += $F[1] / 1024/1024;}elsif ($F[2] eq "mB"){$sum += $F[1]/1024}elsif ($F[2] eq "B"){$sum += $F[1]/1024/1024/1024}}{print int($sum/10)')
CPU_MAX_PCNT=$(grep -c processor /proc/cpuinfo)
MAX_PCNT=${MAX_PCNT:-$CPU_MAX_PCNT}

# start processing exome megafile
EXOME_INPUT="$GNOMAD_RAW_DIR/gnomad.exomes.r${GNOMAD_VERSION}.sites.vcf.bgz"
EXOME_OUTPUT="$GNOMAD_DATA_DIR/gnomad.exomes.r${GNOMAD_VERSION}.norm.vcf.gz"
declare -a EXOME_BY_CHR
# processing chromosomes in parallel, but not too parallel
for i in {1..22} X Y; do
    while [[ $(pcnt) -ge $MAX_PCNT ]]; do
        sleep 15
    done

    log "Processing exome chromosome $i"
    norm_fn="$GNOMAD_RAW_DIR/gnomad.exomes.r${GNOMAD_VERSION}.chr${i}.norm.vcf"
    EXOME_BY_CHR+=($norm_fn)
    normalize_exome_chrom $i $EXOME_INPUT $norm_fn &
    echo $EXOME_INPUT > /dev/null
done

# start processing genome chromosome files

GENOME_OUTPUT="$GNOMAD_DATA_DIR/gnomad.genomes.r${GNOMAD_VERSION}.norm.vcf.gz"
declare -a GENOME_BY_CHR
for j in {1..22} X; do
    while [[ $(pcnt) -ge $MAX_PCNT ]]; do
        sleep 15
    done

    log "Processing genome chromosome $j"
    raw_fn="$GNOMAD_RAW_DIR/gnomad.genomes.r${GNOMAD_VERSION}.sites.chr${j}.vcf.bgz"
    norm_fn="$GNOMAD_RAW_DIR/gnomad.genomes.r${GNOMAD_VERSION}.chr${j}.norm.vcf"
    if [[ -z $BED_REGIONS ]]; then
        bed_opt=""
    else
        bed_opt="-R $BED_REGIONS"
    fi
    GENOME_BY_CHR+=($norm_fn)
    normalize_genome_chrom $raw_fn $norm_fn "$bed_opt" &
done
wait

# zip and index exome data
mkdir -p $GNOMAD_DATA_DIR
log "Zipping ${EXOME_OUTPUT}"
# skip header on all but first file for pipe to bgzip
(cat "${EXOME_BY_CHR[0]}"; grep -hv '^#' "${EXOME_BY_CHR[@]:1}") | $BGZIP --threads ${MAX_ZIP_PCT:-$CPU_MAX_PCNT}> $EXOME_OUTPUT

log "Indexing ${EXOME_OUTPUT}"
$TABIX -p vcf "${EXOME_OUTPUT}"

# zip and index genome data
log "Zipping ${GENOME_OUTPUT}"
(cat "${GENOME_BY_CHR[0]}"; grep -hv '^#' "${GENOME_BY_CHR[@]:1}") | $BGZIP --threads ${MAX_ZIP_PCT:-$CPU_MAX_PCNT}> $GENOME_OUTPUT

log "Indexing ${GENOME_OUTPUT}"
"$TABIX" -p vcf "${GENOME_OUTPUT}"

# cleanup only after everything has succeeded
log "Removing intermediate files"
log "rm -rf $GNOMAD_RAW_DIR"

log "Finished processing gnomAD data"
