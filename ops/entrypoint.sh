#!/bin/bash

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR=$(dirname "$THIS_DIR")

# unpack tarred data, if any
python3 "$ROOT_DIR/unpack_data.py"

exec supervisord -c "$THIS_DIR/supervisor.cfg"
