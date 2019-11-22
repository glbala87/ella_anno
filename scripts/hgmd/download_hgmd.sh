#!/bin/bash -e

# NOT IMPLEMENTED, downstreams steps are complicated and we may be dropping HGMD anyway
# leaving beginning of script here in case we decide to keep HGMD after all

usage() {
    echo
    echo "Usage: $0 < -r RAWDATA_DIR -d DATA_DIR > [ -u HGMD_USER -p HGMD_PASSWORD -x socks5://PROXY_HOST:PROXY_PORT ]"
    echo
    bail
}

bail() {
    if [[ ! -z $1 ]]; then
        echo "ERROR: $1"
    fi
    echo
    exit 1
}

while getopts ":v:r:d:u:p:x:h" opt; do
    case "${opt}" in
        v)
            HGMD_VERSION="$OPTARG"
            ;;
        r)
            RAWDATA_DIR="$OPTARG"
            ;;
        d)
            DATA_DIR="$OPTARG"
            ;;
        u)
            HGMD_USER="$OPTARG"
            ;;
        p)
            HGMD_PASS="$OPTARG"
            ;;
        x)
            export PROXY_ALL="$OPTARG"
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

if [[ -z $HGMD_USER ]] || [[ -z $HGMD_PASS ]]; then
    bail "You must set HGMD_USER and HGMD_PASS with your login information to download data"
fi

if [[ -z $HGMD_VERSION ]]; then
    bail "You must specify the HGMD version number"
elif [[ ! $HGMD_VERSION =~ [0-9]{4}.[0-9]{1,2} ]]; then
    bail "Invalid HGMD_VERSION '$HGMD_VERSION'. Must be format: yyyy.m"
fi

 if [[ -z $RAWDATA_DIR ]]; then
    bail "missing rawdata dir"
else
    mkdir -p "$RAWDATA_DIR"
fi

if [[ -z $DATA_DIR ]]; then
    bail "missing final data dir"
else
    mkdir -p "$DATA_DIR"
fi

BASE_URL=https://portal.biobase-international.com/download/hgmd_data
for db_type in phenbase pro snp views; do
    filename=hgmd_${db_type}-${HGMD_VERSION}.dump.gz
    FILE_URL=$BASE_URL/$HGMD_VERSION/hgmd_${db_type}-${HGMD_VERSION}.dump.gz
    echo "Fetching $FILE_URL"
    curl --user "$HGMD_USER:$HGMD_PASS" "$FILE_URL" -o "$RAWDATA_DIR/$filename"
done

pushd $RAWDATA_DIR
echo "do stuff"

popd
