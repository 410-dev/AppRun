#!/bin/sh
set -eu

export PYTHONPATH="$PWD/src/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
export APPRUN_LANG=en

python3 -m unittest discover -s tests -v
