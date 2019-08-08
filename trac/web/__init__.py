# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

# Workaround for http://bugs.python.org/issue6763 and
# http://bugs.python.org/issue5853 thread issues
import mimetypes
mimetypes.init()

from trac.web.api import *
