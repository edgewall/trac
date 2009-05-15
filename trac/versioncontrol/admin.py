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

from trac.admin import IAdminCommandProvider, get_dir_list
from trac.core import *
from trac.util.text import print_table, printerr, printout
from trac.util.translation import _, ngettext
from trac.versioncontrol import RepositoryManager


class VersionControlAdmin(Component):
    """Version control administration component."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('changeset added', '<repos> <rev> [rev] [...]',
               """Notify trac about changesets added to a repository
               
               This command should be called from a post-commit hook. It will
               trigger a cache update and notify components about the addition.
               """,
               self._complete_repos, self._do_changeset_added)
        yield ('changeset modified', '<repos> <rev> [rev] [...]',
               """Notify trac about changesets modified in a repository
               
               This command should be called from a post-revprop hook after
               revision properties like the commit message, author or date
               have been changed. It will trigger a cache update for the given
               revisions and notify components about the change.
               """,
               self._complete_repos, self._do_changeset_modified)
        yield ('repository add', '<repos> <dir> [type]',
               'Add a source repository',
               self._complete_add, self._do_add)
        yield ('repository alias', '<repos> <alias>',
               'Create an alias for a repository',
               self._complete_repos, self._do_alias)
        yield ('repository list', '',
               'List source repositories',
               None, self._do_list)
        yield ('repository remove', '<repos>',
               'Remove a source repository',
               self._complete_repos, self._do_remove)
        yield ('repository rename', '<repos> <newname>',
               'Rename a source repository',
               self._complete_repos, self._do_rename)
        yield ('repository resync', '<repos> [rev]',
               """Re-synchronize trac with repositories
               
               When [rev] is specified, only that revision is synchronized.
               Otherwise, the complete revision history is synchronized. Note
               that this operation can take a long time to complete.
               If synchronization gets interrupted, it can be resumed later
               using the `sync` command.
               
               To synchronize all repositories, specify "*" as the repository.
               """,
               self._complete_repos, self._do_resync)
        yield ('repository sync', '<repos> [rev]',
               """Resume synchronization of repositories
               
               Similar to `resync`, but doesn't clear the already synchronized
               changesets. Useful for resuming an interrupted `resync`.
               
               To synchronize all repositories, specify "*" as the repository.
               """,
               self._complete_repos, self._do_sync)
    
    def get_supported_types(self):
        rm = RepositoryManager(self.env)
        return [type_ for connector in rm.connectors
                for (type_, prio) in connector.get_supported_types()
                if prio >= 0]
    
    def get_reponames(self):
        rm = RepositoryManager(self.env)
        return [reponame or '(default)' for reponame
                in rm.get_all_repositories()]
    
    def _complete_add(self, args):
        if len(args) == 2:
            return get_dir_list(args[-1], True)
        elif len(args) == 3:
            return self.get_supported_types()
    
    def _complete_repos(self, args):
        if len(args) == 1:
            return self.get_reponames()
    
    def _do_changeset_added(self, reponame, *revs):
        rm = RepositoryManager(self.env)
        rm.notify('changeset_added', reponame, revs, None)
    
    def _do_changeset_modified(self, reponame, *revs):
        rm = RepositoryManager(self.env)
        rm.notify('changeset_modified', reponame, revs, None)
    
    def _do_add(self, reponame, dir, type_=None):
        if reponame == '(default)':
            reponame = ''
        if type_ is not None and type_ not in self.get_supported_types():
            raise TracError(_("The repository type '%(type)s' is not "
                              "supported", type=type_))
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO repository (id, name, value) "
                           "VALUES (%s, %s, %s)",
                           [(reponame, 'dir', dir), (reponame, 'type', type_)])
        db.commit()
        RepositoryManager(self.env).reload_repositories()
    
    def _do_alias(self, reponame, alias):
        if reponame == '(default)':
            reponame = ''
        if alias in ('', '(default)'):
            raise TracError(_("Invalid alias name '%(alias)s'", alias=alias))
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.executemany("INSERT INTO repository (id, name, value) "
                           "VALUES (%s, %s, %s)",
                           [(alias, 'dir', None), (alias, 'alias', reponame)])
        db.commit()
        RepositoryManager(self.env).reload_repositories()
    
    def _do_list(self):
        rm = RepositoryManager(self.env)
        values = []
        for (reponame, info) in sorted(rm.get_all_repositories().iteritems()):
            alias = ''
            if 'alias' in info:
                alias = info['alias'] or '(default)'
            values.append((reponame or '(default)', info.get('type', ''),
                           alias, info.get('dir', '')))
        print_table(values, [_('Name'), _('Type'), _('Alias'), _('Directory')])
    
    def _do_remove(self, reponame):
        if reponame == '(default)':
            reponame = ''
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("DELETE FROM repository "
                       "WHERE id=%s AND name IN ('dir', 'type', 'alias')",
                       (reponame,))
        cursor.execute("DELETE FROM revision WHERE repos=%s", (reponame,))
        cursor.execute("DELETE FROM node_change WHERE repos=%s", (reponame,))
        db.commit()
        RepositoryManager(self.env).reload_repositories()
    
    def _do_rename(self, reponame, newname):
        if reponame == '(default)':
            reponame = ''
        if newname == '(default)':
            newname = ''
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("UPDATE repository SET id=%s WHERE id=%s",
                       (newname, reponame))
        cursor.execute("UPDATE revision SET repos=%s WHERE repos=%s",
                       (newname, reponame))
        cursor.execute("UPDATE node_change SET repos=%s WHERE repos=%s",
                       (newname, reponame))
        db.commit()
        RepositoryManager(self.env).reload_repositories()
    
    def _sync(self, reponame, rev, clean):
        rm = RepositoryManager(self.env)
        if reponame == '*':
            if rev is not None:
                raise TracError(_('Cannot synchronize a single revision '
                                  'on multiple repositories'))
            repositories = rm.get_real_repositories(None)
        else:
            if reponame == '(default)':
                reponame = ''
            repos = rm.get_repository(reponame, None)
            if repos is None:
                raise TracError(_("Unknown repository '%(reponame)s'",
                                  reponame=reponame or '(default)'))
            if rev is not None:
                repos.sync_changeset(rev)
                printout(_('%(rev)s resynced on %(reponame)s.', rev=rev,
                           reponame=repos.reponame or '(default)'))
                return
            repositories = [repos]
        
        from trac.versioncontrol.cache import CACHE_METADATA_KEYS
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        for repos in sorted(repositories, key=lambda r: r.reponame):
            reponame = repos.reponame
            printout(_('Resyncing repository history for %(reponame)s... ',
                       reponame=reponame or '(default)'))
            if clean:
                cursor.execute("DELETE FROM revision WHERE repos=%s",
                               (reponame,))
                cursor.execute("DELETE FROM node_change "
                               "WHERE repos=%s", (reponame,))
                cursor.executemany("DELETE FROM repository "
                                   "WHERE id=%s AND name=%s",
                                   [(reponame, k) for k in CACHE_METADATA_KEYS])
                cursor.executemany("INSERT INTO repository (id, name, value) "
                                   "VALUES (%s, %s, %s)", 
                                   [(reponame, k, '') 
                                    for k in CACHE_METADATA_KEYS])
                db.commit()
            repos.sync(self._sync_feedback)
            cursor.execute("SELECT count(rev) FROM revision WHERE repos=%s",
                           (reponame,))
            for cnt, in cursor:
                printout(ngettext('%(num)s revision cached.',
                                  '%(num)s revisions cached.', num=cnt))
        printout(_('Done.'))

    def _sync_feedback(self, rev):
        sys.stdout.write(' [%s]\r' % rev)
        sys.stdout.flush()

    def _do_resync(self, reponame, rev=None):
        self._sync(reponame, rev, clean=True)

    def _do_sync(self, reponame, rev=None):
        self._sync(reponame, rev, clean=False)

