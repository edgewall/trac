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

from genshi.builder import tag

from trac.admin import IAdminCommandProvider, IAdminPanelProvider
from trac.config import _TRUE_VALUES
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util.text import breakable_path, normalize_whitespace, print_table, \
                           printout
from trac.util.translation import _, ngettext, tag_
from trac.versioncontrol import DbRepositoryProvider, RepositoryManager, \
                                is_default
from trac.web.chrome import Chrome, add_notice, add_warning


class VersionControlAdmin(Component):
    """trac-admin command provider for version control administration."""

    implements(IAdminCommandProvider, IPermissionRequestor)

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
        yield ('repository list', '',
               'List source repositories',
               None, self._do_list)
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
    
    def get_reponames(self):
        rm = RepositoryManager(self.env)
        return [reponame or '(default)' for reponame
                in rm.get_all_repositories()]
    
    def _complete_repos(self, args):
        if len(args) == 1:
            return self.get_reponames()
    
    def _do_changeset_added(self, reponame, *revs):
        if is_default(reponame):
            reponame = ''
        rm = RepositoryManager(self.env)
        rm.notify('changeset_added', reponame, revs)
    
    def _do_changeset_modified(self, reponame, *revs):
        if is_default(reponame):
            reponame = ''
        rm = RepositoryManager(self.env)
        rm.notify('changeset_modified', reponame, revs)
    
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
    
    def _sync(self, reponame, rev, clean):
        rm = RepositoryManager(self.env)
        if reponame == '*':
            if rev is not None:
                raise TracError(_('Cannot synchronize a single revision '
                                  'on multiple repositories'))
            repositories = rm.get_real_repositories()
        else:
            if is_default(reponame):
                reponame = ''
            repos = rm.get_repository(reponame)
            if repos is None:
                raise TracError(_("Repository '%(repo)s' not found",
                                  repo=reponame or '(default)'))
            if rev is not None:
                repos.sync_changeset(rev)
                printout(_('%(rev)s resynced on %(reponame)s.', rev=rev,
                           reponame=repos.reponame or '(default)'))
                return
            repositories = [repos]
        
        db = self.env.get_db_cnx()
        for repos in sorted(repositories, key=lambda r: r.reponame):
            printout(_('Resyncing repository history for %(reponame)s... ',
                       reponame=repos.reponame or '(default)'))
            repos.sync(self._sync_feedback, clean=clean)
            cursor = db.cursor()
            cursor.execute("SELECT count(rev) FROM revision WHERE repos=%s",
                           (repos.id,))
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

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return [('VERSIONCONTROL_ADMIN', ['BROWSER_VIEW', 'CHANGESET_VIEW',
                                          'FILE_VIEW', 'LOG_VIEW'])]


class RepositoryAdminPanel(Component):
    """Web admin panel for repository administration."""

    implements(IAdminPanelProvider)

    # IAdminPanelProvider methods

    def get_admin_panels(self, req):
        if 'VERSIONCONTROL_ADMIN' in req.perm:
            yield ('versioncontrol', _('Version Control'), 'repository',
                   _('Repositories'))
    
    def render_admin_panel(self, req, category, page, path_info):
        req.perm.require('VERSIONCONTROL_ADMIN')
        
        # Retrieve info for all repositories
        rm = RepositoryManager(self.env)
        all_repos = rm.get_all_repositories()
        db_provider = self.env[DbRepositoryProvider]
        
        if path_info:
            # Detail view
            reponame = not is_default(path_info) and path_info or ''
            info = all_repos.get(reponame)
            if info is None:
                raise TracError(_("Repository '%(repo)s' not found",
                                  repo=path_info))
            if req.method == 'POST':
                if req.args.get('cancel'):
                    req.redirect(req.href.admin(category, page))
                
                elif db_provider and req.args.get('save'):
                    # Modify repository
                    changes = {}
                    for field in db_provider.repository_attrs:
                        value = normalize_whitespace(req.args.get(field))
                        if (value is not None or field == 'hidden') \
                                and value != info.get(field):
                            changes[field] = value
                    if changes:
                        db_provider.modify_repository(reponame, changes)
                        add_notice(req, _('Your changes have been saved.'))
                    name = req.args.get('name')
                    resync = tag.tt('trac-admin $ENV repository resync "%s"'
                                    % (name or '(default)'))
                    if 'dir' in changes:
                        msg = tag_('You should now run %(resync)s to '
                                   'synchronize Trac with the repository.',
                                   resync=resync)
                        add_notice(req, msg)
                    elif 'type' in changes:
                        msg = tag_('You may have to run %(resync)s to '
                                   'synchronize Trac with the repository.',
                                   resync=resync)
                        add_notice(req, msg)
                    if name and name != path_info and not 'alias' in info:
                        cset_added = tag.tt('trac-admin $ENV changeset '
                                            'added "%s" $REV'
                                            % (name or '(default)'))
                        msg = tag_('You will need to update your post-commit '
                                   'hook to call %(cset_added)s with the new '
                                   'repository name.', cset_added=cset_added)
                        add_notice(req, msg)
                    req.redirect(req.href.admin(category, page))
            
            Chrome(self.env).add_wiki_toolbars(req)
            data = {'view': 'detail', 'reponame': reponame}
        
        else:
            # List view
            if req.method == 'POST':
                # Add a repository
                if db_provider and req.args.get('add_repos'):
                    name = req.args.get('name')
                    type_ = req.args.get('type')
                    dir = req.args.get('dir')
                    if name is not None and type_ is not None and dir:
                        # Avoid errors when copy/pasting paths
                        dir = normalize_whitespace(dir)
                        db_provider.add_repository(name, dir, type_)
                        name = name or '(default)'
                        add_notice(req, _('The repository "%(name)s" has been '
                                          'added.', name=name))
                        resync = tag.tt('trac-admin $ENV repository resync '
                                        '"%s"' % name)
                        msg = tag_('You should now run %(resync)s to '
                                   'synchronize Trac with the repository.',
                                   resync=resync)
                        add_notice(req, msg)
                        cset_added = tag.tt('trac-admin $ENV changeset '
                                            'added "%s" $REV' % name)
                        msg = tag_('You should also set up a post-commit hook '
                                   'on the repository to call %(cset_added)s '
                                   'for each committed changeset.',
                                   cset_added=cset_added)
                        add_notice(req, msg)
                        req.redirect(req.href.admin(category, page))
                    add_warning(req, _('Missing arguments to add a '
                                       'repository.'))
                
                # Add a repository alias
                elif db_provider and req.args.get('add_alias'):
                    name = req.args.get('name')
                    alias = req.args.get('alias')
                    if name is not None and alias is not None:
                        db_provider.add_alias(name, alias)
                        add_notice(req, _('The alias "%(name)s" has been '
                                          'added.', name=name or '(default)'))
                        req.redirect(req.href.admin(category, page))
                    add_warning(req, _('Missing arguments to add an '
                                       'alias.'))
                
                # Refresh the list of repositories
                elif req.args.get('refresh'):
                    req.redirect(req.href.admin(category, page))
                
                # Remove repositories
                elif db_provider and req.args.get('remove'):
                    sel = req.args.getlist('sel')
                    if sel:
                        for name in sel:
                            db_provider.remove_repository(name)
                        add_notice(req, _('The selected repositories have '
                                          'been removed.'))
                        req.redirect(req.href.admin(category, page))
                    add_warning(req, _('No repositories were selected.'))
            
            data = {'view': 'list'}

        # Find repositories that are editable
        db_repos = {}
        if db_provider is not None:
            db_repos = dict(db_provider.get_repositories())
        
        # Prepare common rendering data
        repositories = dict((reponame, self._extend_info(reponame, info.copy(),
                                                         reponame in db_repos))
                            for (reponame, info) in all_repos.iteritems())
        types = sorted([''] + rm.get_supported_types())
        data.update({'types': types, 'default_type': rm.repository_type,
                     'repositories': repositories})
        
        return 'admin_repositories.html', data

    def _extend_info(self, reponame, info, editable):
        """Extend repository info for rendering."""
        info['name'] = reponame
        if info.get('dir') is not None:
            info['prettydir'] = breakable_path(info['dir']) or ''
        info['hidden'] = info.get('hidden') in _TRUE_VALUES
        info['editable'] = editable
        if not info.get('alias'):
            try:
                repos = RepositoryManager(self.env).get_repository(reponame)
                youngest_rev = repos.get_youngest_rev()
                info['rev'] = youngest_rev
                info['display_rev'] = repos.display_rev(youngest_rev)
            except Exception:
                pass
        return info
