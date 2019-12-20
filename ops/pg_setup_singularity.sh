#!/bin/bash -e

PG_UTA=/pg_uta
DATA_DIR=/anno/data/uta
DEFAULT_DATA=$DATA_DIR/default

rsync -avz $PG_UTA/ $DEFAULT_DATA
chmod -R +r $DEFAULT_DATA
find $DEFAULT_DATA -type d -exec chmod +x {} \+
