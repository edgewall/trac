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
        sudo apt-get install -qq -y libsvn-dev libapr1-dev libaprutil1-dev liblz4-dev libutf8proc-dev swig3.0
        with_apr=/usr/bin/apr-1-config
        with_apr_util=/usr/bin/apu-1-config
        with_swig=/usr/bin/swig3.0
        ;;
      macos-*)
        brew install apr apr-util lz4 utf8proc swig@3
        with_apr="$(brew --prefix apr)/bin/apr-1-config"
        with_apr_util="$(brew --prefix apr-util)/bin/apu-1-config"
        with_swig="$(brew --prefix swig@3)/bin/swig"
        ;;
    esac
    installed_libs="$(pkg-config --list-all |
                      sed -n '/^libsvn_/ { s/ .*$//; p; }' |
                      sort |
                      tr '\n' ',' |
                      sed -e 's/,$//')"

    test -d "$HOME/arc" || mkdir "$HOME/arc"
    curl -s -o "$svntarball" "$svnurl"
    tar xjf "$svntarball" -C "$GITHUB_WORKSPACE"
    cd "$GITHUB_WORKSPACE/subversion-$svnver"
    /bin/sh autogen.sh
    "$python" gen-make.py --installed-libs "$installed_libs"
    ./configure --prefix="$venvdir" \
                --with-apr="$with_apr" \
                --with-apr-util="$with_apr_util" \
                --with-swig="$with_swig" \
                --with-py3c="$GITHUB_WORKSPACE/py3c" \
                --without-apxs \
                --without-doxygen \
                --without-berkeley-db \
                --without-gpg-agent \
                --without-gnome-keyring \
                --without-kwallet \
                --without-jdk \
                PERL=none \
                RUBY=none \
                PYTHON="$python"
    make clean-swig-py
    make -j3 swig_pydir="${sitedir}/libsvn" \
             swig_pydir_extra="${sitedir}/svn" \
             swig-py
    make swig_pydir="${sitedir}/libsvn" \
         swig_pydir_extra="${sitedir}/svn" \
         install-swig-py
    "$python" -c 'from svn import core; print(core.SVN_VERSION)'
    cd "$OLDPWD"
}

init_postgresql() {
    case "$MATRIX_OS" in
      ubuntu-*)
        sudo systemctl start postgresql.service
        ;;
      macos-*)
        rm -rf /usr/local/var/postgres
        pg_ctl initdb --pgdata /usr/local/var/postgres
        pg_ctl -w start --pgdata /usr/local/var/postgres --log /usr/local/var/postgres/postgresql.log || {
            echo "Exited with $?"
            cat /usr/local/var/postgres/postgresql.log
            exit 1
        }
        createuser -s postgres
        ;;
    esac
    {
        case "$MATRIX_OS" in
          ubuntu-*)
            sudo -u postgres psql -e
            ;;
          macos-*)
            psql -U postgres -e
            ;;
        esac
    } <<_EOS_
CREATE USER tracuser NOSUPERUSER NOCREATEDB CREATEROLE PASSWORD 'password';
CREATE DATABASE trac OWNER tracuser;
_EOS_
}

init_mysql() {
    case "$MATRIX_OS" in
      ubuntu-*)
        sudo systemctl start mysql.service
        {
            echo '[client]'
            echo 'host = localhost'
            echo 'user = root'
            echo 'password = root'
        } >~/.my.cnf
        ;;
      macos-*)
        brew install mysql
        mysql.server start
        {
            echo '[client]'
            echo 'host = localhost'
            echo 'user = root'
        } >~/.my.cnf
        ;;
    esac
    mysql -v <<_EOS_
CREATE DATABASE trac DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER tracuser@'%' IDENTIFIED BY 'password';
GRANT ALL ON trac.* TO tracuser@'%';
FLUSH PRIVILEGES;
_EOS_
}

case "$MATRIX_OS" in
  ubuntu-*)
    sudo apt-get update -qq
    sudo apt-get install -qq -y subversion
    ;;
  macos-*)
    HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1
    export HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK
    brew update || :
    brew install subversion
    ;;
esac

venvdir="$HOME/venv"
python -m ensurepip
python -m pip install virtualenv
python -m virtualenv "$venvdir"
python="$venvdir/bin/python"
. "$venvdir/bin/activate"
"$python" -m pip install --upgrade pip setuptools
sitedir="$( \
    "$python" -c \
    'import sys; import distutils.sysconfig as c; print(c.get_python_lib(prefix=sys.argv[1]))' \
    "$venvdir" \
    )"
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
