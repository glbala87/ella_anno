#!/bin/bash -e
set -o pipefail

usage() {
    if [[ -n $* ]]; then
        echo "$*"
    fi
    echo
    echo "    Usage: $(basename "${BASH_SOURCE[0]}") [ -p PKG_NAME -v PKG_VERSION -s -q ]"
    echo
    echo "Optional:"
    echo " -s                Include the total size of the package(s) at the end"
    echo " -p PKG_NAME       Print the size of a specific package"
    echo " -v PKG_VERSION    Check the size of a specific version instead of the current. Only used"
    echo "                   with -p"
    echo " -q                Don't print any log messages, just sizes"
    echo
    echo " -h                Show this help message"
    echo
    exit 1
}

log() {
    echo "$(date -Iseconds) - $*" >&2
}

bail() {
    log " ERROR - $*"
    exit 1
}

# API details: https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjects.html
# ListObjectsV2 not supported on DigitalOcean Spaces
_list_objects() {
    local prefix=$1
    local marker=$2
    local url="${BASE_URL}/?prefix=data/${prefix}&max-keys=1000"
    if [[ -n ${marker} ]]; then
        url="${url}&marker=${marker}"
    fi
    wget -q -O /dev/stdout "${url}"
}

_next_marker() {
    xpath -q -e './/NextMarker/text()' "$1"
}

get_size() {
    if (($# != 2)); then
        bail "Expected 2 args but go $#: '$*'"
    fi
    local pkg=$1
    local ver=$2
    local pkg_prefix resp_file i=0
    declare -a resp_files
    pkg_prefix="$(jq -r ".${pkg}.destination" "${DATASETS}")/${ver}"

    while true; do
        i=$((i + 1))
        resp_file=$(mktemp)
        resp_files+=("${resp_file}")
        _list_objects "${pkg_prefix}" "${next_marker}" >"${resp_file}"
        next_marker="$(_next_marker "${resp_file}")"
        if [[ -z ${next_marker} ]]; then
            break
        fi
    done

    for fname in "${resp_files[@]}"; do
        xpath -q -e './/Contents/Size/text()' "${fname}"
    done | perl -lne '$sum += $_}{print $sum'
}

pprint() {
    local size=$1
    local unit=${2:-MB}
    perl -le '
        %u = (GB => 2**30, MB => 2**20, KB => 2**10);
        printf qq/%0.2f $ARGV[1]\n/, $ARGV[0] / $u{$ARGV[1]};
    ' "${size}" "${unit}"
}

THIS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(dirname "${THIS_DIR}")
DATASETS=${ROOT_DIR}/ops/datasets.json
BASE_URL="https://ella-anno.fra1.digitaloceanspaces.com"

REQ_FILES=("${DATASETS}" "${ROOT_DIR}/ops/install_thirdparty.py")
for fname in "${REQ_FILES[@]}"; do
    if [[ ! -f ${fname} ]]; then
        bail "Could not find required file: ${fname}"
    fi
done

REQ_BINS=(jq wget xpath)
for bname in "${REQ_BINS[@]}"; do
    if ! command -v "${bname}" &>/dev/null; then
        bail "${bname} not installed or not in path"
    fi
done

mapfile -t VALID_PACKAGES < <(jq -rS 'keys[]' "${DATASETS}")
LS_PKGS=("${VALID_PACKAGES[@]}")

while getopts ":p:v:sqh" opt; do
    case "${opt}" in
        p)
            if [[ " ${VALID_PACKAGES[*]} " =~ \ ${OPTARG}\  ]]; then
                LS_PKGS=("${OPTARG}")
            else
                bail "Invalid package: ${OPTARG}"
            fi
            ;;
        v)
            PKG_VER="${OPTARG}"
            ;;
        s)
            SUMMARIZE=1
            ;;
        q)
            QUIET=1
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

declare -A PKG_SIZES
TOTAL_SIZE=0
MAX_WIDTH=0
# debug=0
for pkg_name in "${LS_PKGS[@]}"; do
    if ((${#pkg_name} > MAX_WIDTH)); then
        MAX_WIDTH=${#pkg_name}
    fi

    if [[ ${pkg_name} == "vep" && -z ${PKG_VER} ]]; then
        # vep is "special" aka annoying
        pkg_ver=$(
            PYTHONPATH="${ROOT_DIR}/ops" python -c '
                import install_thirdparty
                print(install_thirdparty.thirdparty_packages["vep"]["version"])
            '
        )
    else
        pkg_ver=${PKG_VER:-$(jq -r ".${pkg_name}.version" "${DATASETS}")}
    fi

    if [[ -z ${QUIET} ]]; then
        log "Fetching size of dataset ${pkg_name} version ${pkg_ver}"
    fi
    PKG_SIZES[${pkg_name}]="$(get_size "${pkg_name}" "${pkg_ver}")"
    TOTAL_SIZE=$((TOTAL_SIZE + ${PKG_SIZES[${pkg_name}]}))

    # debug=$((debug + 1))
    # if ((debug > 3)); then
    #     break
    # fi
done

for lspkg_name in "${LS_PKGS[@]}"; do
    printf "%-${MAX_WIDTH}s  %s\n" "${lspkg_name}" "$(pprint "${PKG_SIZES[${lspkg_name}]}")"
done

if [[ -n ${SUMMARIZE} ]]; then
    pprint "${TOTAL_SIZE}" GB
fi
