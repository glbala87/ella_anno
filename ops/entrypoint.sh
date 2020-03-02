#!/bin/bash

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR=$(dirname "$THIS_DIR")

exec supervisord -c "$THIS_DIR/supervisor.cfg"
