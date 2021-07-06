#!/bin/bash -e

pipenv check

python3 -m pytest /anno/tests/opstests -v
