#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import sys

from setuptools import setup


min_python = (3, 5)
if sys.version_info < min_python:
    print("Trac requires Python %d.%d or later" % min_python)
    sys.exit(1)

extra = {}

try:
    import babel
except ImportError:
    pass
else:
    from trac.dist import get_l10n_trac_cmdclass
    extra['cmdclass'] = get_l10n_trac_cmdclass()

try:
    import jinja2
except ImportError:
    print("Jinja2 is needed by Trac setup, pre-installing")
    # give some context to the warnings we might get when installing Jinja2


setup(**extra)
