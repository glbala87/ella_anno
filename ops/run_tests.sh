#!/bin/bash -e

/anno/ops/pg_startup &

while ! pg_isready --host=$PGDATA --dbname=postgres --username=postgres; do sleep 5; done

VERBOSE=0 SAMPLES=/anno/tests/testdata/sample_repo TARGETS=/anno/tests/testdata/targets python -m pytest /anno/tests/ --ignore /anno/tests/opstests -sv

/anno/ops/pg_shutdown
