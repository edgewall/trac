#! /bin/sh

set -ex

build_svnpy() {
    local svnver_ installed_libs with_apr with_apr_util
    svnver_="$("$python" -c 'import os, svn.core as c; os.write(1, c.SVN_VER_NUMBER)' || :)"
    if [ "$svnver_" = "$svnver" ]; then
        exit 0
    fi

    case "$MATRIX_OS" in
      ubuntu-*)
        sudo apt-get install -qq -y libsvn-dev libapr1-dev libaprutil1-dev liblz4-dev libutf8proc-dev
        with_apr=/usr/bin/apr-1-config
        with_apr_util=/usr/bin/apu-1-config
        with_lz4=std
        with_utf8proc=std
        cflags=''
        ldflags=''
        ;;
      macos-*)
        brew install -q apr apr-util lz4 utf8proc
        with_apr="$(brew --prefix apr)/bin/apr-1-config"
        with_apr_util="$(brew --prefix apr-util)/bin/apu-1-config"
        with_lz4="$(brew --prefix lz4)"
        with_utf8proc="$(brew --prefix utf8proc)"
        cflags="$(pkg-config --cflags-only-I libsvn_subr)"
        ldflags="$(pkg-config --libs-only-L libsvn_subr)"
        ;;
    esac
    installed_libs="$(pkg-config --list-all |
                      sed -n '/^libsvn_/ { s/ .*$//; p; }' |
                      sort |
                      tr '\n' ',' |
                      sed -e 's/,$//')"
    if grep -q 'with-swig-python' configure; then
        opt_swig_python="--with-swig-python=$python"
        opt_swig_perl='--without-swig-perl'
        opt_swig_ruby='--without-swig-ruby'
    else
        opt_swig_python="PYTHON=$python"
        opt_swig_perl='PERL=none'
        opt_swig_ruby='RUBY=none'
    fi

    test -d "$HOME/arc" || mkdir "$HOME/arc"
    curl -s -o "$svntarball" "$svnurl"
    tar xjf "$svntarball" -C "$GITHUB_WORKSPACE"
    cd "$GITHUB_WORKSPACE/subversion-$svnver"
    case "$svnver" in
    1.14.[012])
        git apply -v -p0 --whitespace=fix \
            "$GITHUB_WORKSPACE/.github/svn-swig41.patch" \
            "$GITHUB_WORKSPACE/.github/svn-py312.patch"
        ;;
    esac
    "$python" gen-make.py --release --installed-libs "$installed_libs"
    ./configure --prefix="$venvdir" \
                --with-apr="$with_apr" \
                --with-apr-util="$with_apr_util" \
                --with-lz4="$with_lz4" \
                --with-utf8proc="$with_utf8proc" \
                --with-py3c="$GITHUB_WORKSPACE/py3c" \
                --without-apxs \
                --without-doxygen \
                --without-berkeley-db \
                --without-gpg-agent \
                --without-gnome-keyring \
                --without-kwallet \
                --without-jdk \
                "$opt_swig_python" \
                "$opt_swig_perl" \
                "$opt_swig_ruby" \
                PYTHON="$python" \
                CFLAGS="$cflags" \
                LDFLAGS="$ldflags"
    make -j3 swig_pydir="${sitedir}/libsvn" \
             swig_pydir_extra="${sitedir}/svn" \
             swig-py
    make swig_pydir="${sitedir}/libsvn" \
         swig_pydir_extra="${sitedir}/svn" \
         install-swig-py
    "$python" -c 'from svn import core; print(str(core.SVN_VERSION, "ascii"))'
    cd "$OLDPWD"
}

case "$MATRIX_OS" in
  ubuntu-*)
    sudo apt-get update -qq
    sudo apt-get install -qq -y subversion
    ;;
  macos-*)
    brew update -q || :
    brew install -q subversion
    ;;
esac

venvdir="$HOME/venv"
python -m venv "$venvdir"
python="$venvdir/bin/python"
. "$venvdir/bin/activate"
"$python" -m pip install --upgrade pip setuptools
sitedir="$("$python" -c 'import sysconfig as s; print(s.get_path("purelib"))')"
svnver="$(svn --version --quiet)"
svnurl="https://archive.apache.org/dist/subversion/subversion-$svnver.tar.bz2"
svntarball="$HOME/arc/subversion-$svnver.tar.bz2"

case "$svnver" in
  1.1[0-3].*|1.[0-9].*)
      ;;
  1.*.*)
    build_svnpy
    ;;
esac
