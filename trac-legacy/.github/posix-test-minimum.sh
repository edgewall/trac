#! /bin/sh

set -ex

venvdir="$HOME/venv"
python -m venv "$venvdir"
. "$venvdir/bin/activate"
python="$venvdir/bin/python"
"$python" -m pip install --upgrade pip setuptools
pip install -r .github/requirements-minimum.txt
pip list --format=freeze
{
    echo '.uri ='
    echo 'pythonopts = -Wdefault'
} >Makefile.cfg
make Trac.egg-info
rc=0
make unit-test || rc=$?
if [ "$MATRIX_TESTS" = functional ]; then
    make functional-test testopts=-v || rc=$?
fi
exit $rc
