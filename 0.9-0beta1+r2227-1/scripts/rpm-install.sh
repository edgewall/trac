#! /bin/sh
#
# this file is *inserted* into the install section of the generated
# spec file
#

# this is, what dist.py normally does
./setup.py install --root=${RPM_BUILD_ROOT} --record="INSTALLED_FILES"

# catch compressed man pages
sed -i -e 's@\(.\+/man/man[[:digit:]]/.\+\.[[:digit:]]\)$@\1*@' "INSTALLED_FILES"

# catch any compiled python files (.pyc, .pyo), but don't list them twice
sed -i -e 's@\(.\+\)\.py$@\1.py*@' \
       -e '/.\+\.pyc$/d' \
       "INSTALLED_FILES"
