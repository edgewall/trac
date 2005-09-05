# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import re
import time
import urllib

from trac import util
from trac.util import escape, pretty_timedelta, shorten_line
from trac.wiki import wiki_to_html, wiki_to_oneliner

__all__ = [ 'get_changes', 'get_path_links', 'get_path_rev' ]

rev_re = re.compile(r"([^#]*)#(.+)")

def get_changes(env, repos, revs, full=None, req=None, format=None):
    db = env.get_db_cnx()
    changes = {}
    for rev in revs:
        changeset = repos.get_changeset(rev)
        message = changeset.message
        shortlog = shorten_line(message)        
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
            'age': pretty_timedelta(changeset.date),
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
            'href': escape(href.browser(path, rev=rev))
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

