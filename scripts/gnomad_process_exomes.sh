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
BIN_DIR="$(dirname $THIS_DIR)/bin"
DATA_DIR="$(dirname $THIS_DIR)/data"
FASTA_DIR="$DATA_DIR/FASTA"
GNOMAD_DATA_DIR="$DATA_DIR/variantDBs/gnomAD"
GNOMAD_RAW_DIR="$(dirname $THIS_DIR)/rawdata/gnomAD"

usage() {
    if [[ ! -z $1 ]]; then
        echo "$1"
    fi
    echo
    echo "Usage:"
    echo "    $0 -r GNOMAD_REVISION"
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
    "$TABIX" -p vcf -h "$input_file" $chrom \
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
    BGZIP="$BIN_DIR/bgzip"
else
    bail "Unable to find bgzip in $BIN_DIR"
fi

# memory intensive, can easily use 10GB per normalize_chrom call
# Make sure swap is also enabled or can risk OOM killing by the kernel
SWAP_ON=$(swapon --list 2>&1)
if [[ $SWAP_ON -eq 0 ]]; then
    echo " *** WARNING *** Swap does not appear to be enabled. Processes are likely to be killed by the kernel"
fi
MEM_MAX_PCNT=$(grep -P '(Mem|Swap)Total' /proc/meminfo | perl -lane 'if ($F[2] eq "kB"){$sum += $F[1] / 1024/1024;}elsif ($F[2] eq "mB"){$sum += $F[1]/1024}elsif ($F[2] eq "B"){$sum += $F[1]/1024/1024/1024}}{print int($sum/10)')
CPU_MAX_PCNT=$(grep -c processor /proc/cpuinfo)
MAX_PCNT=${MAX_PCNT:-$MEM_MAX_PCNT}
EXOME_INPUT="$GNOMAD_RAW_DIR/gnomad.exomes.r${GNOMADVERSION}.sites.vcf.bgz"
EXOME_OUTPUT="$GNOMAD_DATA_DIR/gnomad.exomes.r${GNOMADVERSION}.norm.vcf.bgz"
declare -a EXOME_BY_CHR
# processing chromosomes in parallel, but not too parallel
START_HR=$(date +'%b %d %H')
for i in {1..22} X Y; do
    while [[ $(pcnt) -ge $MAX_PCNT ]]; do
        sleep 15
    done

    norm_fn="$GNOMAD_RAW_DIR/gnomad.exomes.r${GNOMADVERSION}.chr${i}.norm.vcf"
    EXOME_BY_CHR+=($norm_fn)
    normalize_chrom $i $EXOME_INPUT $norm_fn &
done
wait

FIN_HR=$(date +'%b %d %H')
# fail on err causes script to exit if no matches are found, so we temporarily disable that
set +e
OOM_CNT=$(grep -Pc "($START_HR|$FIN_HR).+?oom_reaper.+?\(vt\)" /var/log/syslog)
set -e
if [[ $OOM_CNT -gt 0 ]]; then
    echo " *** WARNING *** found ${OOM_CNT} reaped vt processes, output may be incomplete"
fi

mkdir -p $GNOMAD_DATA_DIR
log "Zipping ${EXOME_OUTPUT}"
# skip header on all but first file for pipe to bgzip
(cat "${EXOME_BY_CHR[0]}"; grep -hv '^#' "${EXOME_BY_CHR[@]:1}") | $BGZIP --threads ${MAX_ZIP_PCT:-$CPU_MAX_PCNT}> $EXOME_OUTPUT

log "Indexing ${EXOME_OUTPUT}"
$TABIX -p vcf "${EXOME_OUTPUT}"

# cleanup only after everything has succeeded
log "Removing intermediate files"
rm -rf $GNOMAD_RAW_DIR

log "Finished processing gnomAD exome data"
