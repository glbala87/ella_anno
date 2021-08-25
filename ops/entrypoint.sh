#!/bin/bash

THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$THIS_DIR")

# remove stale postgres lockfiles
for lockfile in $PGDATA/postmaster.pid $PGDATA/.s.PGSQL.*; do
    [ -f "$lockfile" ] && rm "$lockfile"
done

exec supervisord -c "$THIS_DIR/supervisor.cfg"
