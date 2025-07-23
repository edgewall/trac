#! /bin/sh

set -ex

venvdir="$HOME/venv"
python -m venv "$venvdir"
. "$venvdir/bin/activate"
python -m pip install --upgrade pip setuptools
pip install -r requirements-release.txt
pip install setuptools-git
make compile sdist wheel
