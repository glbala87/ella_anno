#!/bin/bash -e

/anno/ops/pg_startup &
/anno/ops/pg_wait 5 60

VERBOSE=0 SAMPLES=/anno/tests/testdata/sample_repo TARGETS=/anno/tests/testdata/targets ANNO_CONFIG_PATH=/anno/tests/testdata/anno_global_config.json python3 -m pytest /anno/tests/ --ignore /anno/tests/opstests -sv

/anno/ops/pg_shutdown
