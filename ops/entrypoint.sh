#!/bin/bash

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# remove stale postgres lockfiles
for lockfile in ${PGDATA}/postmaster.pid "${PGDATA}"/.s.PGSQL.*; do
    if [[ -f "${lockfile}" ]]; then
        rm "${lockfile}"
    fi
done

exec supervisord -c "${THIS_DIR}/supervisor.cfg"
