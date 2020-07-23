# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

import os
import pkg_resources
import sys

from trac.admin import *
from trac.api import IEnvironmentSetupParticipant
from trac.core import *
from trac.wiki import model
from trac.wiki.api import WikiSystem
from trac.util import lazy, read_file
from trac.util.datefmt import format_datetime, from_utimestamp
from trac.util.text import path_to_unicode, print_table, printout, \
                           to_unicode, unicode_quote, unicode_unquote
from trac.util.translation import _


class WikiAdmin(Component):
    """trac-admin command provider for wiki administration."""

    implements(IAdminCommandProvider, IEnvironmentSetupParticipant)

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        yield ('wiki list', '',
               'List wiki pages',
               None, self._do_list)
        yield ('wiki rename', '<page> <new_name>',
               'Rename wiki page',
               self._complete_page, self._do_rename)
        yield ('wiki remove', '<page>',
               'Remove wiki page',
               self._complete_page, self._do_remove)
        yield ('wiki export', '<page> [file]',
               'Export wiki page to file or stdout',
               self._complete_import_export, self._do_export)
        yield ('wiki import', '<page> [file]',
               'Import wiki page from file or stdin',
               self._complete_import_export, self._do_import)
        yield ('wiki dump', '<directory> [page] [...]',
               """Export wiki pages to files named by title

               Individual wiki page names can be specified after the directory.
               A name ending with a * means that all wiki pages starting with
               that prefix should be dumped. If no name is specified, all wiki
               pages are dumped.""",
               self._complete_dump, self._do_dump)
        yield ('wiki load', '<path> [...]',
               """Import wiki pages from files

               If a given path is a file, it is imported as a page with the
               name of the file. If a path is a directory, all files in that
               directory are imported.""",
               self._complete_load_replace, self._do_load)
        yield ('wiki replace', '<path> [...]',
               """Replace content of wiki pages from files (DANGEROUS!)

               This command replaces the content of the last version of one
               or more wiki pages with new content. The previous content is
               lost, and no new entry is created in the page history. The
               metadata of the page (time, author) is not changed either.

               If a given path is a file, it is imported as a page with the
               name of the file. If a path is a directory, all files in that
               directory are imported.

               WARNING: This operation results in the loss of the previous
               content and cannot be undone. It may be advisable to backup
               the current content using "wiki dump" beforehand.""",
               self._complete_load_replace, self._do_replace)
        yield ('wiki upgrade', '',
               'Upgrade default wiki pages to current version',
               None, self._do_upgrade)

    @lazy
    def default_pages_dir(self):
        return pkg_resources.resource_filename('trac.wiki', 'default-pages')

    def get_wiki_list(self, prefix=None):
        return sorted(WikiSystem(self.env).get_pages(prefix))

    def export_page(self, page, filename):
        wikipage = model.WikiPage(self.env, page)
        if wikipage.exists:
            if not filename:
                printout(wikipage.text)
            else:
                if os.path.isfile(filename):
                    raise AdminCommandError(_("File '%(name)s' exists",
                                              name=path_to_unicode(filename)))
                with open(filename, 'w') as f:
                    f.write(wikipage.text.encode('utf-8'))
        else:
            raise AdminCommandError(_("Page '%(page)s' not found", page=page))

    def import_page(self, filename, title, create_only=[], replace=False):
        if filename:
            if not os.path.isfile(filename):
                raise AdminCommandError(_("'%(name)s' is not a file",
                                          name=path_to_unicode(filename)))
            data = read_file(filename)
        else:
            data = sys.stdin.read()
        data = to_unicode(data, 'utf-8')
        name = unicode_unquote(title.encode('utf-8'))

        page = model.WikiPage(self.env, name)
        if page.exists:
            if name in create_only:
                self.log.info("%s already exists", name)
                return False
            if data == page.text:
                self.log.info("%s is already up to date", name)
                return False

        page.text = data
        try:
            page.save('trac', None, replace=replace)
        except TracError as e:
            raise AdminCommandError(e)

        self.log.info("%s imported from %s", name, path_to_unicode(filename))
        return True

    def load_pages(self, dir, ignore=[], create_only=[], replace=False):
        loaded = []
        with self.env.db_transaction:
            for page in sorted(os.listdir(dir)):
                if page in ignore:
                    continue
                filename = os.path.join(dir, page)
                if os.path.isfile(filename):
                    page = unicode_unquote(page.encode('utf-8'))
                    if self.import_page(filename, page, create_only, replace):
                        loaded.append(page)
        return loaded

    def _complete_page(self, args):
        if len(args) == 1:
            return self.get_wiki_list()

    def _complete_import_export(self, args):
        if len(args) == 1:
            return self.get_wiki_list()
        elif len(args) == 2:
            return get_dir_list(args[-1])

    def _complete_dump(self, args):
        if len(args) == 1:
            return get_dir_list(args[-1], dirs_only=True)
        elif len(args) >= 2:
            return self.get_wiki_list()

    def _complete_load_replace(self, args):
        if len(args) >= 1:
            return get_dir_list(args[-1])

    def _do_list(self):
        print_table(
            [(title, int(edits), format_datetime(from_utimestamp(modified),
                                                 console_datetime_format))
             for title, edits, modified in self.env.db_query("""
                    SELECT name, max(version), max(time)
                    FROM wiki GROUP BY name ORDER BY name""")
             ], [_("Title"), _("Edits"), _("Modified")])

    def _do_rename(self, name, new_name):
        page = model.WikiPage(self.env, name)
        try:
            page.rename(new_name)
        except TracError as e:
            raise AdminCommandError(e)
        printout(_(" '%(name1)s' renamed to '%(name2)s'",
                   name1=name, name2=new_name))

    def _do_remove(self, name):
        with self.env.db_transaction:
            if name.endswith('*'):
                pages = self.get_wiki_list(name.rstrip('*') or None)
                for p in pages:
                    page = model.WikiPage(self.env, p)
                    page.delete()
                print_table(((p,) for p in pages), [_('Deleted pages')])
            else:
                page = model.WikiPage(self.env, name)
                page.delete()
                printout(_(" '%(page)s' deleted", page=name))

    def _do_export(self, page, filename=None):
        self.export_page(page, filename)
        if filename:
            printout(" '%s' => '%s'" % (page, filename))

    def _do_import(self, page, filename=None):
        self._import(filename, page)

    def _do_dump(self, directory, *names):
        if not names:
            names = ['*']
        pages = self.get_wiki_list()
        if not os.path.isdir(directory):
            if not os.path.exists(directory):
                os.mkdir(directory)
            else:
                raise AdminCommandError(_("'%(name)s' is not a directory",
                                          name=path_to_unicode(directory)))
        for p in pages:
            if any(p == name or
                   name.endswith('*') and p.startswith(name[:-1])
                   for name in names):
                dst = os.path.join(directory, unicode_quote(p, ''))
                printout(" '%s' => '%s'" % (p, dst))
                self.export_page(p, dst)

    def _do_load(self, *paths):
        self._load_or_replace(paths, replace=False)

    def _do_replace(self, *paths):
        self._load_or_replace(paths, replace=True)

    def _do_upgrade(self):
        names = self.load_pages(self.default_pages_dir,
                                ignore=['WikiStart', 'SandBox'],
                                create_only=['InterMapTxt'])
        printout(_("Upgrade done: %(count)s pages upgraded.",
                   count=len(names)))

    def _import(self, filename, title, replace=False):
        if self.import_page(filename, title, replace=replace):
            printout(" '%s' => '%s'" % (path_to_unicode(filename), title))
        else:
            printout(_(" '%(title)s' is already up to date", title=title))

    def _load_or_replace(self, paths, replace):
        with self.env.db_transaction:
            for path in paths:
                if os.path.isdir(path):
                    for page in sorted(os.listdir(path)):
                        filename = os.path.join(path, page)
                        if os.path.isfile(filename):
                            self._import(filename, page, replace)
                else:
                    page = os.path.basename(path)
                    self._import(path, page, replace)

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Add default wiki pages when environment is created."""
        self.log.info("Installing default wiki pages")
        with self.env.db_transaction:
            for name in self.load_pages(self.default_pages_dir):
                if name not in ('InterMapTxt', 'SandBox', 'WikiStart'):
                    page = model.WikiPage(self.env, name)
                    page.readonly = 1
                    page.save(None, None)

    def environment_needs_upgrade(self):
        pass

    def upgrade_environment(self):
        pass
