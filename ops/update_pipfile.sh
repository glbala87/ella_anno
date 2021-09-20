#!/bin/bash -ex

# This should ONLY be run inside one of the Docker containers built using the Makefile

# tell pipenv where Pipfile is so it doesn't have to search
export PIPENV_PIPFILE=${PIPENV_PIPFILE:-/anno/Pipfile}
LOCAL_PIPFILE=/local_anno/Pipfile

# if mounted in Pipfile doesn't match the image's Pipfile, use the local
# one instead. Useful when there isn't a branch image available.
update_pipfile() {
    if ! diff -q "${LOCAL_PIPFILE}" "${PIPENV_PIPFILE}" >/dev/null 2>&1; then
        cp "${LOCAL_PIPFILE}" "${PIPENV_PIPFILE}"
    fi
}

check_packages() {
    if pipenv update --outdated --dev; then
        echo "No packages to update"
        return 1
    fi
}

do_update() {
    # save the existing venv in case we want to compare
    VENV_DIR=$(readlink -f "$(pipenv --venv)")
    if [[ -d "${VENV_DIR}" ]]; then
        mv "${VENV_DIR}" "${VENV_DIR}.old"
    fi

    # nuke the existing lockfile and start fresh
    mv "${PIPENV_PIPFILE}.lock" "${PIPENV_PIPFILE}.lock.old"

    VIRTUAL_ENV="" pipenv lock --dev

    # copy to locally mounted
    cp "${PIPENV_PIPFILE}.lock" /local_anno/
}

update_pipfile
check_packages
do_update
