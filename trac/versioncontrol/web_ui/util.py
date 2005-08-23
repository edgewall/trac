# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import re
import time
import urllib

from trac import util
from trac.wiki import wiki_to_html, wiki_to_oneliner

__all__ = [ 'get_changes', 'get_path_links', 'get_path_rev' ]

rev_re = re.compile(r"([^#]+)#(.+)")

def get_changes(env, repos, revs, full=None, req=None, format=None):
    db = env.get_db_cnx()
    changes = {}
    for rev in revs:
        changeset = repos.get_changeset(rev)
        message = changeset.message
        shortlog = util.shorten_line(message)        
        files = None
        if format == 'changelog':
            files = [change[0] for change in changeset.get_changes()]
        elif message:
            if not full:
                message = wiki_to_oneliner(shortlog, env, db)
            else:
                message = wiki_to_html(message, env, req, db,
                                       absurls=(format == 'rss'),
                                       escape_newlines=True)
        if not message:
            message = '--'
        changes[rev] = {
            'date_seconds': changeset.date,
            'date': time.strftime('%x %X', time.localtime(changeset.date)),
            'age': util.pretty_timedelta(changeset.date),
            'author': changeset.author or 'anonymous',
            'shortlog': shortlog,
            'message': message,
            'files': files
        }
    return changes

def get_path_links(href, path, rev):
    links = []
    parts = path.split('/')
    if not parts[-1]:
        parts.pop()
    path = '/'
    for part in parts:
        path = path + part + '/'
        links.append({
            'name': part or 'root',
            'href': href.browser(path, rev=rev)
        })
    return links

def get_path_rev(path):
    rev = None
    match = rev_re.search(path)
    if match:
        path = match.group(1)
        rev = match.group(2)
    path = urllib.unquote(path)
    return (path, rev)

