# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import pkg_resources

from trac.core import *
from trac.web.chrome import ITemplateProvider


class VersionControlUI(Component):

    implements(ITemplateProvider)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.versioncontrol',
                                                'templates')]
