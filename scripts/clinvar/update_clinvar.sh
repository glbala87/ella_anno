#!/bin/bash

# ClinVar is officially updated on first Thursday each month
# We run this script by a cron job two days after first Thursday(first/second Saturday) each month
#  0 0 3-9 * * [ "$(date '+\%a')" = "Sat" ] && /path/to/repo/amg/src/clinvar/clinvar_update.sh > /path/to/repo/amg/src/clinvar/clinvar_update.log 2>&1
# numpy is required, can use a virutalenv ('db-update' in this script) or install numpy system wide

set -e

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR=$(dirname "$(dirname $THIS_DIR)")
BIN_DIR=$ROOT_DIR/bin
RAWDATA_DIR=$ROOT_DIR/rawdata/clinvar
DATA_DIR=$ROOT_DIR/data/variantDBs/clinvar
FASTA_DIR=$ROOT_DIR/data/FASTA

# DB update working dir
ANNODBDIR="/home/xuyang/AnnoDB"

log() {
    echo "[$$] $(date +%Y-%m-%d\ %H:%M:%S) - $1"
}

bail() {
    echo "*** ERROR *** $1"
    exit 1
}

if [[ -f "$BIN_DIR/tabix" ]]; then
    TABIX=$BIN_DIR/tabix
else
    bail "No tabix at $BIN_DIR"
fi

if [[ -f "$BIN_DIR/bgzip" ]]; then
    BGZIP=$BIN_DIR/bgzip
else
    bail "No bgzip at $BIN_DIR"
fi

if [[ -f "$BIN_DIR/vt" ]]; then
    VT=$BIN_DIR/vt
else
    bail "No vt at $BIN_DIR"
fi

# move to working dir
TODAY=$(date +%Y%m%d)
REF_GENOME=$FASTA_DIR/human_g1k_v37_decoy.fasta
CLINVAR_XML="$RAWDATA_DIR/ClinVarFullRelease_00-latest.xml.gz"
CLINVAR_VCF="$RAWDATA_DIR/clinvar_${TODAY}.vcf"
CLINVAR_GZ="$CLINVAR_VCF.gz"
CLINVAR_NORM="$RAWDATA_DIR/clinvar_${TODAY}_norm.vcf"
CLINVAR_NORM_GZ="$DATA_DIR/$(basename $CLINVAR_NORM).gz"

# download latest clinvar xml
log "Fetching latest ClinVar release"
wget "ftp://ftp.ncbi.nlm.nih.gov/pub/clinvar/xml/$(basename $CLINVAR_XML)" -O "$RAWDATA_DIR/$CLINVAR_XML"

log "Converting $CLINVAR_XML to $CLINVAR_VCF"
"${THIS_DIR}/clinvardb_to_vcf.py" -o "$CLINVAR_VCF" -i "$CLINVAR_XML" -g "$REF_GENOME"

# sort, bgzip and tabix for vt
log "Sorting, zipping and indexing $CLINVAR_VCF"
(grep '^#' "$CLINVAR_VCF"; grep -v '^#' "$CLINVAR_VCF" | sort -T $ANNODBDIR -k1,1V -k2,2n -s) | $BGZIP > "$CLINVAR_GZ"
$TABIX -p vcf $CLINVAR_GZ

# decompose and normalize by vt
log "Decompose and normalize $CLINVAR_GZ"
$VT decompose -s "$CLINVAR_GZ" | $VT normalize -n -r "$REF_GENOME" - > "$CLINVAR_NORM"

# sort, bgzip and tabix of the result vcf
log "Sorting, zipping and indexing of $CLINVAR_NORM"
(grep '^#' "$CLINVAR_NORM"; grep -v '^#' "$CLINVAR_NORM" | sort -T $ANNODBDIR -k1,1V -k2,2n -s) | $BGZIP > "$CLINVAR_NORM_GZ"
$VCBIN/bin/tabix -p vcf "$CLINVAR_NORM_GZ"

# cleanup
log "Removing intermediate files"
rm -rf $RAWDATA_DIR

log "ClinVar update completed"
