#!/bin/bash -e

# download gnomAD from http://gnomad.broadinstitute.org/downloads
#
# gnomAD keeps changing file name formats. This version is configured for the 2.0.2 release

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR=$(dirname "$(dirname $THIS_DIR)")
DATA_DIR=$ROOT_DIR/rawdata/gnomAD

usage() {
    if [[ ! -z $1 ]]; then
        echo "$1"
    fi
    echo
    echo USAGE:
    echo "    $0 < -r GNOMAD_REVISION > [ -s/--skip-md5 ] "
    echo
    exit 1
}

log() {
    echo "[$$] $(date +%Y-%m-%d\ %H:%M:%S) - $1"
}

pcnt() {
    CNT=$(pgrep -P $$ | wc -l)
    echo $((CNT - 1))
}

rm_on_mismatch() {
    local_file="$1"
    remote_hash="$2"
    local_hash=$(openssl dgst -md5 -binary $local_file | openssl enc -base64)
    if [[ "$local_hash" != "$remote_hash" ]]; then
        rm $local_file # (hash mismatch)
    else
        log "Skipping already downloaded file: $(basename $local_file)"
    fi
}

while [ $# -gt 0 ]; do
  key="$1"
  case "$key" in
    -r|--revision)
      REVISION="$2"
      shift 2
      ;;
    -s|--skip-md5)
        SKIP_MD5=1
        shift
        ;;
    -h|--help)
        usage
        ;;
    *)
      break
      ;;
  esac
done

if [[ -z "$REVISION" ]]; then
  usage "Error! revision is missing, e.g. 2.0.2"
fi

GSUTIL=$(which gsutil 2>/dev/null)
if [[ -z $GSUTIL ]]; then
    usage "Unable to find gsutil, make sure it is installed, in the PATH and try again"
fi

# set -x
mkdir -p $DATA_DIR
MAX_PCNT=${MAX_PCNT:-$(grep -c processor /proc/cpuinfo)}
GS_FILES=($($GSUTIL ls gs://gnomad-public/release/${REVISION}/vcf/exomes/gnomad.exomes.r${REVISION}.sites.vcf.bgz* \
    gs://gnomad-public/release/${REVISION}/vcf/genomes/gnomad.genomes.r${REVISION}.sites.chr*.vcf.bgz*))
# go through all the files listed remotely and check for any that already exist locally
# If filename exists, compare filesize and md5sum (unless set to skip md5 check)
# * If both values match, keep the local file and don't download
# * Otherwise, delete the local file and download a new copy
for gs_file in "${GS_FILES[@]}"; do
    local_file=$GNOMAD_DATA_DIR/$(basename $gs_file)
    if [[ -f $local_file ]]; then
        # compare file size for faster exclusion
        gs_file_size=$($GSUTIL du $gs_file | cut -f1 -d' ')

        if [[ $gs_file_size -eq $(stat -c %s $local_file) ]]; then
            if [[ -z $SKIP_MD5 ]]; then
                # checksum is single thread and slow, so let's parallelize what we can but not kill the CPU
                while [[ $(pcnt) -ge $MAX_PCNT ]]; do
                    sleep 15
                done

                gs_file_hash=$($GSUTIL hash $gs_file | grep '(md5)' | perl -lane 'print $F[-1]')
                rm_on_mismatch $local_file $gs_file_hash &
            fi
        else
            rm $local_file # (size mismatch)
        fi
    fi
done
wait

LOCAL_FILES=($(ls $DATA_DIR))
for local_file in "${LOCAL_FILES[@]}"; do
    for i in "${!GS_FILES[@]}"; do
        if [[ "$(basename ${GS_FILES[i]})" == "$local_file" ]]; then
            unset "GS_FILES[$i]"
        fi
    done
done

# download all new files in a parallel manner
if [[ ${#GS_FILES[@]} -gt 0 ]]; then
    log "Downloading ${#GS_FILES[@]} gnomAD files"
    $GSUTIL -m cp "${GS_FILES[@]}" $DATA_DIR
else
    echo "All gnomAD files already downloaded"
fi
