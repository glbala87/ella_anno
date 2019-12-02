#!/bin/bash -e

python3 /anno/unpack_lfs.py

/anno/ops/pg_startup &

while ! pg_isready --dbname=postgres --username=postgres; do sleep 5; done

VERBOSE=0 SAMPLES=/anno/tests/testdata/sample_repo TARGETS=/anno/tests/testdata/targets py.test /anno/tests/ -sv
