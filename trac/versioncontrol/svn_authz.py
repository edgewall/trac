# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2019 Edgewall Software
# Copyright (C) 2004 Francois Harvey <fharvey@securiweb.net>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Francois Harvey <fharvey@securiweb.net>
#         Matthew Good <trac@matt-good.net>

import os.path

from trac.config import ConfigurationError, Option, ParsingError, \
                        PathOption, UnicodeConfigParser
from trac.core import Component, TracError, implements
from trac.perm import IPermissionPolicy
from trac.util import pathjoin, to_list
from trac.util.text import exception_to_unicode
from trac.versioncontrol.api import RepositoryManager


def parent_iter(path):
    while 1:
        yield path
        if path == '/':
            return
        path = path[:-1]
        yield path
        idx = path.rfind('/')
        path = path[:idx + 1]


def parse(authz_file, modules):
    """Parse a Subversion authorization file.

    Return a dict of modules, each containing a dict of paths, each containing
    a dict mapping users to permissions. Only modules contained in `modules`
    are retained.
    """
    parser = UnicodeConfigParser(ignorecase_option=False)
    parser.read(authz_file)

    groups = {}
    aliases = {}
    sections = {}
    for section in parser.sections():
        if section == 'groups':
            for name, value in parser.items(section):
                groups.setdefault(name, set()).update(to_list(value))
        elif section == 'aliases':
            for name, value in parser.items(section):
                aliases[name] = value.strip()
        else:
            for name, value in parser.items(section):
                parts = section.split(':', 1)
                module, path = parts[0] if len(parts) > 1 else '', parts[-1]
                if module in modules:
                    sections.setdefault((module, path), []) \
                            .append((name, value))

    def resolve(subject, done):
        if subject.startswith('@'):
            done.add(subject)
            for members in groups[subject[1:]] - done:
                for each in resolve(members, done):
                    yield each
        elif subject.startswith('&'):
            yield aliases[subject[1:]]
        else:
            yield subject

    authz = {}
    for (module, path), items in sections.iteritems():
        section = authz.setdefault(module, {}).setdefault(path, {})
        for subject, perms in items:
            readable = 'r' in perms
            # Ordering isn't significant; any entry could grant permission
            section.update((user, readable)
                           for user in resolve(subject, set())
                           if not section.get(user))
    return authz


class AuthzSourcePolicy(Component):
    """Permission policy for `source:` and `changeset:` resources using a
    Subversion authz file.

    `FILE_VIEW` and `BROWSER_VIEW` permissions are granted as specified in the
    authz file.

    `CHANGESET_VIEW` permission is granted for changesets where `FILE_VIEW` is
    granted on at least one modified file, as well as for empty changesets.
    """

    implements(IPermissionPolicy)

    authz_file = PathOption('svn', 'authz_file', '',
        """The path to the Subversion
        [%(svnbook)s authorization (authz) file].
        To enable authz permission checking, the `AuthzSourcePolicy`
        permission policy must be added to `[trac] permission_policies`.
        Non-absolute paths are relative to the Environment `conf`
        directory.
        """,
        doc_args={'svnbook': 'http://svnbook.red-bean.com/en/1.7/'
                             'svn.serverconfig.pathbasedauthz.html'})

    authz_module_name = Option('svn', 'authz_module_name', '',
        """The module prefix used in the `authz_file` for the default
        repository. If left empty, the global section is used.
        """)

    _handled_perms = frozenset([(None, 'BROWSER_VIEW'),
                                (None, 'CHANGESET_VIEW'),
                                (None, 'FILE_VIEW'),
                                (None, 'LOG_VIEW'),
                                ('source', 'BROWSER_VIEW'),
                                ('source', 'FILE_VIEW'),
                                ('source', 'LOG_VIEW'),
                                ('changeset', 'CHANGESET_VIEW')])

    def __init__(self):
        self._mtime = 0
        self._authz = {}
        self._users = set()

    # IPermissionPolicy methods

    def check_permission(self, action, username, resource, perm):
        realm = resource.realm if resource else None
        if (realm, action) in self._handled_perms:
            authz, users = self._get_authz_info()
            if authz is None:
                return False

            if username == 'anonymous':
                usernames = '$anonymous', '*'
            else:
                usernames = username, '$authenticated', '*'
            if resource is None:
                return True if users & set(usernames) else None

            rm = RepositoryManager(self.env)
            try:
                repos = rm.get_repository(resource.parent.id)
            except TracError:
                return True  # Allow error to be displayed in the repo index
            if repos is None:
                return True
            modules = [resource.parent.id or self.authz_module_name]
            if modules[0]:
                modules.append('')

            def check_path_0(spath):
                sections = [authz.get(module, {}).get(spath)
                            for module in modules]
                sections = [section for section in sections if section]
                denied = False
                for user in usernames:
                    for section in sections:
                        if user in section:
                            if section[user]:
                                return True
                            denied = True
                            # Don't check section without module name
                            # because the section with module name defines
                            # the user's permissions.
                            break
                if denied:  # All users has no readable permission.
                    return False

            def check_path(path):
                path = '/' + pathjoin(repos.scope, path)
                if path != '/':
                    path += '/'

                # Allow access to parent directories of allowed resources
                for spath in set(sum((list(authz.get(module, {}))
                                      for module in modules), [])):
                    if spath.startswith(path):
                        result = check_path_0(spath)
                        if result is True:
                            return True

                # Walk from resource up parent directories
                for spath in parent_iter(path):
                    result = check_path_0(spath)
                    if result is not None:
                        return result

            if realm == 'source':
                return check_path(resource.id)

            elif realm == 'changeset':
                changes = list(repos.get_changeset(resource.id).get_changes())
                if not changes or any(check_path(change[0])
                                      for change in changes):
                    return True

    def _get_authz_info(self):
        if not self.authz_file:
            self.log.error("The [svn] authz_file configuration option in "
                           "trac.ini is empty or not defined")
            raise ConfigurationError()
        try:
            mtime = os.path.getmtime(self.authz_file)
        except OSError as e:
            self.log.error("Error accessing svn authz permission policy "
                           "file: %s", exception_to_unicode(e))
            raise ConfigurationError()
        if mtime != self._mtime:
            self._mtime = mtime
            rm = RepositoryManager(self.env)
            modules = set(repos.reponame
                          for repos in rm.get_real_repositories())
            if '' in modules and self.authz_module_name:
                modules.add(self.authz_module_name)
            modules.add('')
            self.log.info("Parsing authz file: %s", self.authz_file)
            try:
                self._authz = parse(self.authz_file, modules)
            except ParsingError as e:
                self.log.error("Error parsing svn authz permission policy "
                               "file: %s", exception_to_unicode(e))
                raise ConfigurationError()
            else:
                self._users = {user
                               for paths in self._authz.itervalues()
                               for path in paths.itervalues()
                               for user, result in path.iteritems()
                               if result}
        return self._authz, self._users
