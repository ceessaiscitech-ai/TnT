#!/usr/bin/env bash
# install_and_test_linux.sh -- v20.49: install R, every package, Jupyter + the R kernel, then run the complete R test.
# For a Linux machine / Colab / a code sandbox WITH internet (run from the R folder):  bash tests/install_and_test_linux.sh [quick]
# (v20.49: libglpk for HonestDiD's Rglpk -- without it M34 failed on pooled data; 'quick' skips the 96 notebook runs)
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends r-base-core r-base-dev pandoc libgdal-dev libgeos-dev libproj-dev libudunits2-dev \
  libcurl4-openssl-dev libssl-dev libxml2-dev libglpk-dev libgmp-dev libzmq3-dev python3-pip > /dev/null
# CRAN packages as pre-built Linux binaries (Posit Package Manager) -- minutes instead of an hour of compiling
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
Rscript -e "options(repos = c(CRAN = 'https://packagemanager.posit.co/cran/__linux__/${CODENAME}/latest'), HTTPUserAgent = sprintf('R/%s R (%s)', getRversion(), paste(getRversion(), R.version\$platform, R.version\$arch, R.version\$os))); source('00_SETUP.R')"
pip install --quiet --break-system-packages jupyterlab nbconvert ipykernel
Rscript -e "IRkernel::installspec(user = FALSE)"
Rscript tests/run_all_tests.R "$@"
