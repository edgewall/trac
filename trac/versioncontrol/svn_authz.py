# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2009 Edgewall Software
# Copyright (C) 2004 Francois Harvey <fharvey@securiweb.net>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Francois Harvey <fharvey@securiweb.net>
#         Matthew Good <trac@matt-good.net>

import os.path

from trac.config import Option, PathOption
from trac.core import *
from trac.perm import IPermissionPolicy
from trac.resource import Resource
from trac.util import read_file
from trac.util.compat import any
from trac.util.text import exception_to_unicode, to_unicode
from trac.util.translation import _
from trac.versioncontrol.api import RepositoryManager


def parent_iter(path):
    path = path.strip('/')
    if path:
        path = '/' + path + '/'
    else:
        path = '/'

    while 1:
        yield path
        if path == '/':
            return
        path = path[:-1]
        yield path
        idx = path.rfind('/')
        path = path[:idx + 1]


class ParseError(Exception):
    """Exception thrown for parse errors in authz files"""


def parse(authz):
    """Parse a Subversion authorization file.
    
    Return a dict of modules, each containing a dict of paths, each containing
    a dict mapping users to permissions.
    """
    groups = {}
    aliases = {}
    sections = {}
    section = None
    lineno = 0
    for line in authz.splitlines():
        lineno += 1
        line = to_unicode(line.strip())
        if not line or line.startswith('#') or line.startswith(';'):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            continue
        if section is None:
            raise ParseError(_('Line %(lineno)d: Entry before first '
                               'section header', lineno=lineno))
        parts = line.split('=', 1)
        if len(parts) != 2:
            raise ParseError(_('Line %(lineno)d: Invalid entry',
                               lineno=lineno))
        name, value = parts
        name = name.strip()
        if section == 'groups':
            group = groups.setdefault(name, set())
            group.update(each.strip() for each in value.split(','))
        elif section == 'aliases':
            aliases[name] = value.strip()
        else:
            sections.setdefault(section, []).append((name.strip(), value))

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
    for name, items in sections.iteritems():
        parts = name.split(':', 1)
        module = authz.setdefault(len(parts) > 1 and parts[0] or '', {})
        section = module.setdefault(parts[-1], {})
        for subject, perms in items:
            for user in resolve(subject, set()):
                section.setdefault(user, 'r' in perms)  # The first match wins
    
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
    
    authz_file = PathOption('trac', 'authz_file', '',
        """The path to the Subversion
        [http://svnbook.red-bean.com/en/1.5/svn.serverconfig.pathbasedauthz.html authorization (authz) file].
        To enable authz permission checking, the `AuthzSourcePolicy` permission
        policy must be added to `[trac] permission_policies`.
        """)

    authz_module_name = Option('trac', 'authz_module_name', '',
        """The module prefix used in the `authz_file` for the default
        repository. If left empty, the global sections will be used.
        """)

    _mtime = 0
    _authz = {}
    _users = set()
    
    # IPermissionPolicy methods

    def check_permission(self, action, username, resource, perm):
        if action == 'FILE_VIEW' or action == 'BROWSER_VIEW':
            authz, users = self._get_authz_info()
            if authz is None:
                return False
            if resource is None:
                return users is True or username in users
            if resource.realm == 'source':
                modules = [resource.parent.id or self.authz_module_name]
                if modules[0]:
                    modules.append('')
                for p in parent_iter(resource.id):
                    for module in modules:
                        section = authz.get(module, {}).get(p, {})
                        result = section.get(username)
                        if result is not None:
                            return result
                        result = section.get('*')
                        if result is not None:
                            return result
                return False
        elif action == 'CHANGESET_VIEW':
            authz, users = self._get_authz_info()
            if authz is None:
                return False
            if resource is None:
                return users is True or username in users
            if resource.realm == 'changeset':
                rm = RepositoryManager(self.env)
                repos = rm.get_repository(resource.parent.id)
                changes = list(repos.get_changeset(resource.id).get_changes())
                if not changes:
                    return True
                source = Resource('source', version=resource.id,
                                  parent=resource.parent)
                return any('FILE_VIEW' in perm(source(id=change[0]))
                           for change in changes)

    def _get_authz_info(self):
        try:
            mtime = os.path.getmtime(self.authz_file)
        except OSError, e:
            if self._authz is not None:
                self.log.error('Error accessing authz file: %s',
                               exception_to_unicode(e))
            self._mtime = mtime = 0
            self._authz = None
            self._users = set()
        if mtime > self._mtime:
            self._mtime = mtime
            self.log.info('Parsing authz file: %s' % self.authz_file)
            try:
                self._authz = parse(read_file(self.authz_file))
                users = set(user for module in self._authz.itervalues()
                            for path in module.itervalues()
                            for user, result in path.iteritems() if result)
                self._users = '*' in users or users
            except Exception, e:
                self._authz = None
                self._users = set()
                self.log.error('Error parsing authz file: %s',
                               exception_to_unicode(e))
        return self._authz, self._users
