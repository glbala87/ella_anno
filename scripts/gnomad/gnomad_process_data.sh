#!/bin/bash

# gnomAD exomes is downloaded as one single file with all chromosomes
#  remove histogram fields and VEP annotation (CSQ field)
#  decompose and normalize by vt
#  bgzip
#  tabix

set -e -o pipefail

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$(dirname "${THIS_DIR}")")
DATA_DIR=${ROOT_DIR}/data
FASTA_DIR=${DATA_DIR}/FASTA
GNOMAD_DATA_DIR=${DATA_DIR}/variantDBs/gnomAD
GNOMAD_RAW_DIR=${ROOT_DIR}/rawdata/gnomad

usage() {
    if [[ -n "$*" ]]; then
        echo "$*"
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
    echo "[$$] $(date +%Y-%m-%d\ %H:%M:%S) - $*"
}

bail() {
    echo "$*"
    exit 1
}

pcnt() {
    CNT=$(pgrep -P $$ | wc -l)
    echo $((CNT - 1))
}

check_tmp() {
    df /tmp | perl -lane '$MIN_GB=50;next if ($. == 1);if ($F[3] < $MIN_GB * 1024*1024) { print STDERR " *** ERROR *** Insufficient disk space for sorting gnomAD genomic output, set TMP_DIR when running make commands"; exit 1}'
}

normalize_chrom() {
    local chrom=$1
    local input_file=$2
    local output_file=$3
    local bed_opt=$4
    tabix -p vcf -h "${bed_opt}" "${input_file}" "${chrom}" \
        | perl -F'\t' -wlane 'if (substr($F[0], 0, 1) eq "#"){print join("\t", @F)}else{print join("\t", @F[0..6], join(";", (grep { ! /^(GQ_HIST_ALT|DP_HIST_ALT|AB_HIST_ALT|GQ_HIST_ALL|DP_HIST_ALL|AB_HIST_ALL|CSQ)=/ } (split ";", $F[7]))))}' \
        | vt decompose -s - \
        | vt normalize -r "${REFERENCE}" -n -w 20000 - \
        | vcf-sort -t "${TMP_DIR:-/tmp}" \
            >"${output_file}" \
        || bail "Error processing chrom ${chrom} of ${input_file}, return code: $?"
    log "Finished processing chromosome ${chrom} of ${input_file}"
}

while getopts ":v:b:h" opt; do
    case "${opt}" in
        v)
            GNOMAD_VERSION="${OPTARG}"
            ;;
        b)
            BED_REGIONS="${OPTARG}"
            ;;
        h)
            usage
            ;;
        \?)
            usage "Invalid option: ${OPTARG}"
            ;;
        :)
            usage "Missing argument for ${OPTARG}"
            ;;
    esac
done

REFERENCE=${FASTA_DIR}/human_g1k_v37_decoy.fasta.gz
if [[ ! -f "${REFERENCE}" ]]; then
    usage "Error! Unable to find reference genome: '${REFERENCE}', check it was synced correctly"
fi

if [[ -z "${GNOMAD_VERSION}" ]]; then
    usage "Error! gnomAD version missing."
fi

if [[ -z "${BED_REGIONS}" ]]; then
    echo "Warning: no bed file specified. Genomic output will be very large"
elif [[ ! -f "${BED_REGIONS}" ]]; then
    usage "Error! Unable to find bed file: ${BED_REGIONS}"
fi

for tool in tabix vt bgzip vcf-sort; do
    if [[ -z $(which ${tool} 2>/dev/null) ]]; then
        bail "Unable to find ${tool} in ${PATH}"
    fi
done

# Estimate max parallel procs based on CPU as limiting resource
# though I/O is likely to be main chokepoint unless running on lots of SSDs
CPU_MAX_PCNT=$(nproc)
MAX_PCNT=${MAX_PCNT:-${CPU_MAX_PCNT}}

# start processing exome megafile
EXOME_INPUT="${GNOMAD_RAW_DIR}/gnomad.exomes.r${GNOMAD_VERSION}.sites.vcf.bgz"
EXOME_OUTPUT="${GNOMAD_DATA_DIR}/gnomad.exomes.r${GNOMAD_VERSION}.norm.vcf.gz"
declare -a EXOME_BY_CHR
# processing chromosomes in parallel, but not too parallel
for i in {1..22} X Y; do
    while [[ $(pcnt) -ge ${MAX_PCNT} ]]; do
        sleep 15
    done

    log "Processing exome chromosome ${i}"
    norm_fn="${GNOMAD_RAW_DIR}/gnomad.exomes.r${GNOMAD_VERSION}.chr${i}.norm.vcf"
    EXOME_BY_CHR+=("${norm_fn}")
    if [[ -f ${norm_fn} ]]; then
        log "skipping existing file ${norm_fn}"
    else
        normalize_chrom ${i} "${EXOME_INPUT}" "${norm_fn}" &
    fi
done

# start processing genome chromosome files

GENOME_OUTPUT="${GNOMAD_DATA_DIR}/gnomad.genomes.r${GNOMAD_VERSION}.norm.vcf.gz"
declare -a GENOME_BY_CHR
for j in {1..22} X; do
    while [[ $(pcnt) -ge ${MAX_PCNT} ]]; do
        sleep 15
    done

    log "Processing genome chromosome ${j}"
    raw_fn="${GNOMAD_RAW_DIR}/gnomad.genomes.r${GNOMAD_VERSION}.sites.chr${j}.vcf.bgz"
    norm_fn="${GNOMAD_RAW_DIR}/gnomad.genomes.r${GNOMAD_VERSION}.chr${j}.norm.vcf"
    if [[ -z ${BED_REGIONS} ]]; then
        bed_opt=""
    else
        bed_opt="-R ${BED_REGIONS}"
    fi
    GENOME_BY_CHR+=("${norm_fn}")
    if [[ -f ${norm_fn} ]]; then
        log "skipping existing file ${norm_fn}"
    else
        check_tmp || bail
        normalize_chrom ${j} "${raw_fn}" "${norm_fn}" "${bed_opt}" &
    fi
done
wait

# zip and index exome data
mkdir -p "${GNOMAD_DATA_DIR}"
log "Zipping ${EXOME_OUTPUT}"
# skip header on all but first file for pipe to bgzip
if [[ ! -f ${EXOME_OUTPUT} ]]; then
    (
        cat "${EXOME_BY_CHR[0]}"
        grep -hv '^#' "${EXOME_BY_CHR[@]:1}"
    ) | bgzip --threads "${MAX_ZIP_PCT:-${CPU_MAX_PCNT}}" >"${EXOME_OUTPUT}"
else
    echo "Merged gzipped exome data already existing, skipping"
fi

log "Indexing ${EXOME_OUTPUT}"
tabix -p vcf -f "${EXOME_OUTPUT}"
tabix -p vcf --csi -f "${EXOME_OUTPUT}"

# zip and index genome data
log "Zipping ${GENOME_OUTPUT}"
if [[ ! -f ${GENOME_OUTPUT} ]]; then
    (
        cat "${GENOME_BY_CHR[0]}"
        grep -hv '^#' "${GENOME_BY_CHR[@]:1}"
    ) | bgzip --threads "${MAX_ZIP_PCT:-${CPU_MAX_PCNT}}" ">${GENOME_OUTPUT}"
else
    echo "Merged gzipped genome data already exists, skipping"
fi

log "Indexing ${GENOME_OUTPUT}"
tabix -p vcf -f "${GENOME_OUTPUT}"
tabix -p vcf --csi -f "${GENOME_OUTPUT}"

log "Finished processing gnomAD data"
