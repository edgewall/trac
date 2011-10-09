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

from datetime import datetime
import os.path
import pkg_resources
import sys

from trac.admin import *
from trac.core import *
from trac.wiki import model
from trac.wiki.api import WikiSystem, validate_page_name
from trac.util import read_file
from trac.util.compat import any
from trac.util.datefmt import format_datetime, from_utimestamp, \
                              to_utimestamp, utc
from trac.util.text import path_to_unicode, print_table, printout, \
                           to_unicode, unicode_quote, unicode_unquote
from trac.util.translation import _


class WikiAdmin(Component):
    """trac-admin command provider for wiki administration."""

    implements(IAdminCommandProvider)

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
               """Replace the content of wiki pages from files (DANGEROUS!)
               
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
    
    def get_wiki_list(self):
        return list(WikiSystem(self.env).get_pages())
    
    def export_page(self, page, filename, cursor=None):
        if cursor is None:
            db = self.env.get_db_cnx()
            cursor = db.cursor()
        cursor.execute("SELECT text FROM wiki WHERE name=%s "
                       "ORDER BY version DESC LIMIT 1", (page,))
        for text, in cursor:
            break
        else:
            raise AdminCommandError(_("Page '%(page)s' not found", page=page))
        if not filename:
            printout(text)
        else:
            if os.path.isfile(filename):
                raise AdminCommandError(_("File '%(name)s' exists",
                                          name=path_to_unicode(filename)))
            f = open(filename, 'w')
            try:
                f.write(text.encode('utf-8'))
            finally:
                f.close()
    
    def import_page(self, filename, title, create_only=[],
                    replace=False):
        if not validate_page_name(title):
            raise AdminCommandError(_("Invalid Wiki page name '%(name)s'",
                                      name=title))
        if filename:
            if not os.path.isfile(filename):
                raise AdminCommandError(_("'%(name)s' is not a file",
                                          name=path_to_unicode(filename)))
            data = read_file(filename)
        else:
            data = sys.stdin.read()
        data = to_unicode(data, 'utf-8')

        result = [True]
        @self.env.with_transaction()
        def do_import(db):
            cursor = db.cursor()
            # Make sure we don't insert the exact same page twice
            cursor.execute("SELECT text FROM wiki WHERE name=%s "
                           "ORDER BY version DESC LIMIT 1",
                           (title,))
            old = list(cursor)
            if old and title in create_only:
                printout(_('  %(title)s already exists', title=title))
                result[0] = False
                return
            if old and data == old[0][0]:
                printout(_('  %(title)s is already up to date', title=title))
                result[0] = False
                return
        
            if replace and old:
                cursor.execute("UPDATE wiki SET text=%s WHERE name=%s "
                               "  AND version=(SELECT max(version) FROM wiki "
                               "               WHERE name=%s)",
                               (data, title, title))
            else:
                cursor.execute("INSERT INTO wiki(version,name,time,author,"
                               "                 ipnr,text) "
                               "SELECT 1+COALESCE(max(version),0),%s,%s,"
                               "       'trac','127.0.0.1',%s FROM wiki "
                               "WHERE name=%s",
                               (title, to_utimestamp(datetime.now(utc)), data,
                                title))
            if not old:
                del WikiSystem(self.env).pages
        return result[0]

    def load_pages(self, dir, ignore=[], create_only=[], replace=False):
        @self.env.with_transaction()
        def do_load(db):
            for page in os.listdir(dir):
                if page in ignore:
                    continue
                filename = os.path.join(dir, page)
                page = unicode_unquote(page.encode('utf-8'))
                if os.path.isfile(filename):
                    if self.import_page(filename, page, create_only, replace):
                        printout(_("  %(page)s imported from %(filename)s",
                                   filename=path_to_unicode(filename),
                                   page=page))
    
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
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name, max(version), max(time) "
                       "FROM wiki GROUP BY name ORDER BY name")
        print_table([(r[0], int(r[1]),
                      format_datetime(from_utimestamp(r[2]),
                                      console_datetime_format))
                     for r in cursor],
                    [_('Title'), _('Edits'), _('Modified')])
    
    def _do_rename(self, name, new_name):
        if new_name == name:
            return
        if not new_name:
            raise AdminCommandError(_('A new name is mandatory for a rename.'))
        if not validate_page_name(new_name):
            raise AdminCommandError(_("The new name is invalid."))
        @self.env.with_transaction()
        def do_rename(db):
            if model.WikiPage(self.env, new_name, db=db).exists:
                raise AdminCommandError(_('The page %(name)s already exists.',
                                          name=new_name))
            page = model.WikiPage(self.env, name, db=db)
            page.rename(new_name)

    def _do_remove(self, name):
        @self.env.with_transaction()        
        def do_transaction(db):
            if name.endswith('*'):
                pages = list(WikiSystem(self.env).get_pages(name.rstrip('*')
                                                            or None))
                for p in pages:
                    page = model.WikiPage(self.env, p, db=db)
                    page.delete()
                print_table(((p,) for p in pages), [_('Deleted pages')])
            else:
                page = model.WikiPage(self.env, name, db=db)
                page.delete()
    
    def _do_export(self, page, filename=None):
        self.export_page(page, filename)
    
    def _do_import(self, page, filename=None):
        self.import_page(filename, page)
    
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
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        for p in pages:
            if any(p == name or (name.endswith('*')
                                 and p.startswith(name[:-1]))
                   for name in names):
                dst = os.path.join(directory, unicode_quote(p, ''))
                printout(' %s => %s' % (p, dst))
                self.export_page(p, dst, cursor)
    
    def _load_or_replace(self, paths, replace):
        @self.env.with_transaction()
        def do_transaction(db):
            for path in paths:
                if os.path.isdir(path):
                    self.load_pages(path, replace=replace)
                else:
                    page = os.path.basename(path)
                    page = unicode_unquote(page.encode('utf-8'))
                    if self.import_page(path, page, replace=replace):
                        printout(_("  %(page)s imported from %(filename)s",
                                   filename=path_to_unicode(path), page=page))
    
    def _do_load(self, *paths):
        self._load_or_replace(paths, replace=False)
    
    def _do_replace(self, *paths):
        self._load_or_replace(paths, replace=True)
    
    def _do_upgrade(self):
        self.load_pages(pkg_resources.resource_filename('trac.wiki',
                                                        'default-pages'),
                        ignore=['WikiStart', 'checkwiki.py'],
                        create_only=['InterMapTxt'])
