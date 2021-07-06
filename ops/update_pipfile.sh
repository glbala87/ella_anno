#!/bin/bash -e

# This should ONLY be run inside one of the Docker containers built using the Makefile

# tell pipenv where Pipfile is so it doesn't have to search
export PIPENV_PIPFILE=${PIPENV_PIPFILE:-/anno/Pipfile}
# override the values set in the Dockerfile so pipenv doesn't get confused
export PATH=$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset VIRTUAL_ENV

check_packages() {
    if pipenv update --outdated --dev; then
        echo "No packages to update"
        return 1
    fi
}

do_update() {
    # save the existing venv in case we want to compare
    VENV_DIR=$(readlink -f "$(pipenv --venv)")
    if [[ -d "$VENV_DIR" ]]; then
        mv "$VENV_DIR" "${VENV_DIR}.old"
    fi

    # nuke the existing lockfile and start fresh
    mv "$PIPENV_PIPFILE.lock" "$PIPENV_PIPFILE.lock.old"

    pipenv install --dev

    # copy to locally mounted
    cp "$PIPENV_PIPFILE.lock" /local_anno/
}

check_packages
do_update
