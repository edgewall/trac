# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import shutil

from trac.util import create_unique_file
from trac.util.text import exception_to_unicode


def backup_config_file(env, suffix):
    try:
        backup, f = create_unique_file(env.config.filename + suffix)
        f.close()
        shutil.copyfile(env.config.filename, backup)
        env.log.info("Saved backup of configuration file in %s", backup)
    except IOError as e:
        env.log.warn("Couldn't save backup of configuration file (%s)",
                     exception_to_unicode(e))
