#! /bin/sh

set -ex

venvdir="$HOME/venv"
python -m ensurepip
python -m pip install virtualenv
python -m virtualenv "$venvdir"
. "$venvdir/bin/activate"
python="$venvdir/bin/python"
"$python" -m pip install --upgrade pip setuptools
pip install -r .github/requirements-minimum.txt
pip list --format=freeze

echo '.uri =' >Makefile.cfg
PYTHONWARNINGS=default
export PYTHONWARNINGS
make Trac.egg-info
rc=0
make unit-test || rc=$?
if [ "$MATRIX_TESTS" = functional ]; then
    PYTHONWARNINGS=ignore
    make functional-test testopts=-v || rc=$?
fi
exit $rc
