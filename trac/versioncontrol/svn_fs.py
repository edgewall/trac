# -*- coding: utf-8 -*-
#
# Copyright (C) 2012 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.util import import_namespace
import_namespace(globals(), 'tracopt.versioncontrol.svn.svn_fs')

# This module is a stub provided for backward compatibility. The svn_fs
# module has been moved to tracopt.versioncontrol.svn. Please update your
# code to use the new location.
