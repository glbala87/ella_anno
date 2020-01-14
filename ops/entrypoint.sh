#!/bin/bash

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR=$(dirname "$THIS_DIR")

# unpack tarred data, if any
python3 "$ROOT_DIR/unpack_data.py"

if [[ -z $PGONLY ]]; then
    CFG="$THIS_DIR/supervisor.cfg"
else
    CFG="$THIS_DIR/supervisor-postgres.cfg"
fi
exec supervisord -c "$CFG"
