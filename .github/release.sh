#! /bin/sh

set -ex

venvdir="$HOME/venv"
python -m ensurepip
python -m pip install virtualenv
python -m virtualenv "$venvdir"
. "$venvdir/bin/activate"
python -m pip install --upgrade pip setuptools
pip install -r requirements-release.txt
pip install setuptools-git
make compile sdist wheel
