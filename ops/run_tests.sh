#!/bin/bash -e

/anno/ops/pg_startup &
/anno/ops/pg_wait 5 60

# env vars required by anno config parser
export SAMPLE_ID="Diag-wgs1-NA12878"
export GP_NAME="Ciliopati"
export GP_VERSION="v06"
export TYPE="single"
export CAPTUREKIT="wgs"
export ANNO_CONFIG_PATH="/anno/tests/testdata/anno_global_config.json"

VERBOSE=0 SAMPLES=/anno/tests/testdata/sample_repo TARGETS=/anno/tests/testdata/targets python3 -m pytest /anno/tests/ --ignore /anno/tests/opstests -sv

/anno/ops/pg_shutdown
