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
import time

from trac.admin import *
from trac.core import *
from trac.wiki import model
from trac.wiki.api import WikiSystem
from trac.util.datefmt import format_datetime, utc
from trac.util.text import to_unicode, unicode_quote, unicode_unquote, \
                           print_table, printout
from trac.util.translation import _


class WikiAdmin(Component):
    """Wiki administration component."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods
    
    def get_admin_commands(self):
        yield ('wiki list', '',
               'List wiki pages',
               None, self._do_list)
        yield ('wiki remove', '<page>',
               'Remove wiki page',
               self._complete_remove, self._do_remove)
        yield ('wiki export', '<page> [file]',
               'Export wiki page to file or stdout',
               self._complete_import_export, self._do_export)
        yield ('wiki import', '<page> [file]',
               'Import wiki page from file or stdin',
               self._complete_import_export, self._do_import)
        yield ('wiki dump', '<directory>',
               'Export all wiki pages to files named by title',
               self._complete_dump_load, self._do_dump)
        yield ('wiki load', '<directory>',
               'Import all wiki pages from directory',
               self._complete_dump_load, self._do_load)
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
        text = cursor.fetchone()[0]
        if not filename:
            printout(text)
        else:
            if os.path.isfile(filename):
                raise AdminCommandError(_("File '%(name)s' exists",
                                          name=filename))
            f = open(filename, 'w')
            try:
                f.write(text.encode('utf-8'))
            finally:
                f.close()
    
    def import_page(self, filename, title, db=None, create_only=[]):
        if not os.path.isfile(filename):
            raise AdminCommandError(_("'%(name)s' is not a file",
                                      name=filename))
        
        f = open(filename, 'r')
        try:
            data = to_unicode(f.read(), 'utf-8')
        finally:
            f.close()
        
        # Make sure we don't insert the exact same page twice
        handle_ta = not db
        if handle_ta:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT text FROM wiki WHERE name=%s "
                       "ORDER BY version DESC LIMIT 1",
                       (title,))
        old = list(cursor)
        if old and title in create_only:
            printout('  %s already exists.' % title)
            return False
        if old and data == old[0][0]:
            printout('  %s already up to date.' % title)
            return False
        
        cursor.execute("INSERT INTO wiki(version,name,time,author,ipnr,text) "
                       " SELECT 1+COALESCE(max(version),0),%s,%s,"
                       " 'trac','127.0.0.1',%s FROM wiki "
                       " WHERE name=%s",
                       (title, int(time.time()), data, title))
        if not old:
            WikiSystem(self.env).pages.invalidate(db)
        if handle_ta:
            db.commit()
        return True

    def load_pages(self, dir, db=None, ignore=[], create_only=[]):
        cons_charset = getattr(sys.stdout, 'encoding', None) or 'utf-8'
        for page in os.listdir(dir):
            if page in ignore:
                continue
            filename = os.path.join(dir, page)
            page = unicode_unquote(page.encode('utf-8'))
            if os.path.isfile(filename):
                if self.import_page(filename, page, db, create_only):
                    printout(_("  %(page)s imported from %(filename)s",
                               filename=filename, page=page))
    
    def _complete_remove(self, args):
        if len(args) == 1:
            return self.get_wiki_list()
    
    def _complete_import_export(self, args):
        if len(args) == 1:
            return self.get_wiki_list()
        elif len(args) == 2:
            return get_dir_list(args[-1])
    
    def _complete_dump_load(self, args):
        if len(args) == 1:
            return get_dir_list(args[-1], True)
    
    def _do_list(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT name, max(version), max(time) "
                       "FROM wiki GROUP BY name ORDER BY name")
        print_table([(r[0], int(r[1]),
                      format_datetime(datetime.fromtimestamp(r[2], utc),
                                      console_datetime_format))
                     for r in cursor],
                    [_('Title'), _('Edits'), _('Modified')])
    
    def _do_remove(self, name):
        db = self.env.get_db_cnx()
        if name.endswith('*'):
            pages = list(WikiSystem(self.env).get_pages(name.rstrip('*')
                                                        or None))
            for p in pages:
                page = model.WikiPage(self.env, p, db=db)
                page.delete(db=db)
            print_table(((p,) for p in pages), [_('Deleted pages')])
        else:
            page = model.WikiPage(self.env, name, db=db)
            page.delete(db=db)
        db.commit()
    
    def _do_export(self, page, filename=None):
        self.export_page(page, filename)
    
    def _do_import(self, page, filename=None):
        self.import_page(filename, page)
    
    def _do_dump(self, directory):
        pages = self.get_wiki_list()
        if not os.path.isdir(directory):
            if not os.path.exists(directory):
                os.mkdir(directory)
            else:
                raise AdminCommandError(_("'%(name)s' is not a directory",
                                          name=directory))
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        for p in pages:
            dst = os.path.join(directory, unicode_quote(p, ''))
            printout(' %s => %s' % (p, dst))
            self.export_page(p, dst, cursor)
    
    def _do_load(self, directory):
        db = self.env.get_db_cnx()
        self.load_pages(directory, db)
        db.commit()
    
    def _do_upgrade(self):
        db = self.env.get_db_cnx()
        self.load_pages(pkg_resources.resource_filename('trac.wiki', 
                                                        'default-pages'),
                        db, ignore=['WikiStart', 'checkwiki.py'],
                        create_only=['InterMapTxt'])
        db.commit()
