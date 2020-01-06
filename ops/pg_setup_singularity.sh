#!/bin/bash -e

PG_UTA=/pg_uta
SGL_BASE=/anno/singularity
SGL_DEFAULT=$SGL_BASE/default

# The Docker image is mid-process when the singularity image is build, so we need start and clean shutdown postgres
# to make sure the data is in good condition
export PG_DATA_DUMP=1
/anno/ops/pg_startup &
/anno/ops/pg_shutdown

# copy UTA data out
mkdir -p $SGL_DEFAULT
rsync -az /var/run/postgresql $PG_UTA $SGL_DEFAULT/ --info=progress2
chmod 2775 $SGL_DEFAULT/postgresql
chmod -R +r $SGL_DEFAULT
find $SGL_DEFAULT -type d -exec chmod +x {} \+

# remove data from $PG_UTA since we'll be mounting it in on top anyway
rm -rf "${PG_UTA:?}/*"
