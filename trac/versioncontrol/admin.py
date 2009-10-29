# -*- coding: utf-8 -*-
#
# Copyright (C) 2008 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import sys

from trac.admin import IAdminCommandProvider
from trac.core import *
from trac.util.text import printout
from trac.util.translation import _, ngettext


class VersionControlAdmin(Component):
    """Version control administration component."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('resync', '[rev]',
               """Re-synchronize trac with the repository
               
               When [rev] is specified, only that revision is synchronized.
               Otherwise, the complete revision history is synchronized. Note
               that this operation can take a long time to complete.
               """,
               None, self._do_resync)
    
    def _do_resync(self, rev=None):
        if rev:
            self.env.get_repository().sync_changeset(rev)
            printout(_('%(rev)s resynced.', rev=rev))
            return
        from trac.versioncontrol.cache import CACHE_METADATA_KEYS
        printout(_('Resyncing repository history... '))
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("DELETE FROM revision")
        cursor.execute("DELETE FROM node_change")
        cursor.executemany("DELETE FROM system WHERE name=%s",
                           [(k,) for k in CACHE_METADATA_KEYS])
        cursor.executemany("INSERT INTO system (name, value) VALUES (%s, %s)",
                           [(k, '') for k in CACHE_METADATA_KEYS])
        db.commit()
        self.env.get_repository().sync(self._resync_feedback)
        cursor.execute("SELECT count(rev) FROM revision")
        for cnt, in cursor:
            printout(ngettext('%(num)s revision cached.',
                              '%(num)s revisions cached.', num=cnt))
        printout(_('Done.'))

    def _resync_feedback(self, rev):
        sys.stdout.write(' [%s]\r' % rev)
        sys.stdout.flush()
