# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import shutil

from trac.util.compat import close_fds


# On Windows, shutil.rmtree doesn't remove files with the read-only
# attribute set, so this function explicitly removes it on every error
# before retrying.  Even on Linux, shutil.rmtree chokes on read-only
# directories, so we use this version in all cases.
# Fix from http://bitten.edgewall.org/changeset/521
def rmtree(root):
    """Catch shutil.rmtree failures on Windows when files are read-only."""
    def _handle_error(fn, path, excinfo):
        os.chmod(path, 0666)
        fn(path)
    return shutil.rmtree(root, onerror=_handle_error)

