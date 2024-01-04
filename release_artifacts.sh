#!/bin/bash
VERSION="${1:-latest}"

command -v python3 >/dev/null 2>&1 || { echo >&2 "I require Python3 but it's not installed.  Aborting."; exit 1; }

if ! command -v cargo &> /dev/null;
then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh  # install cargo for pyapp
fi

/usr/bin/env python3 -m venv ./venv && \
    source ./venv/bin/activate && \
    python3 -m pip install --upgrade pip setuptools wheel && \
    python3 -m pip install build shiv twine && \
    python3 -m shiv --compressed --reproducible -c tidal-wave -o ~/tools/tidal-wave_${VERSION}.pyz .  && \  # shiv executable
    PYAPP_PROJECT_NAME=tidal-wave PYAPP_PROJECT_VERSION=${VERSION} cargo install pyapp --root out && \
    mv out/bin/pyapp ~/tools/tidal-wave_${VERSION}.pyapp && \
    PYAPP_PROJECT_NAME=tidal-wave PYAPP_PROJECT_VERSION=${VERSION} PYAPP_FULL_ISOLATION=1 PYAPP_DISTRIBUTION_EMBED=1 PYAPP_PYTHON_VERSION=3.11 cargo install pyapp --root out && \
    mv out/bin/pyapp ~/tools/tidal-wave_${VERSION}_py311.pyapp && \
    rm -r out/
