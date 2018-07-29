# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from pkg_resources import DistributionNotFound, get_distribution

try:
    __version__ = get_distribution('Trac').version
except DistributionNotFound:
    __version__ = '1.2.3'
