# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
#         Christian Boos <cboos@neuf.fr>

import re
import urllib

from trac.core import TracError
from trac.util.datefmt import format_datetime, pretty_timedelta
from trac.util.text import shorten_line
from trac.util.markup import escape, html, Markup
from trac.versioncontrol.api import NoSuchNode, NoSuchChangeset
from trac.wiki import wiki_to_html, wiki_to_oneliner

__all__ = ['get_changes', 'get_path_links', 'get_path_rev_line',
           'get_existing_node', 'render_node_property']

def get_changes(env, repos, revs, full=None, req=None, format=None):
    db = env.get_db_cnx()
    changes = {}
    for rev in revs:
        try:
            changeset = repos.get_changeset(rev)
        except NoSuchChangeset:
            changes[rev] = {}
            continue

        wiki_format = env.config['changeset'].getbool('wiki_format_messages')
        message = changeset.message or '--'
        absurls = (format == 'rss')
        if wiki_format:
            shortlog = wiki_to_oneliner(message, env, db,
                                        shorten=True, absurls=absurls)
        else:
            shortlog = Markup.escape(shorten_line(message))

        if full:
            if wiki_format:
                message = wiki_to_html(message, env, req, db,
                                       absurls=absurls, escape_newlines=True)
            else:
                message = html.PRE(message)
        else:
            message = shortlog

        if format == 'rss':
            if isinstance(shortlog, Markup):
                shortlog = shortlog.plaintext(keeplinebreaks=False)
            message = unicode(message)

        changes[rev] = {
            'date_seconds': changeset.date,
            'date': format_datetime(changeset.date),
            'age': pretty_timedelta(changeset.date),
            'author': changeset.author or 'anonymous',
            'message': message, 'shortlog': shortlog,
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

rev_re = re.compile(r"([^@#:]*)[@#:]([^#]+)(?:#L(\d+))?")

def get_path_rev_line(path):
    rev = None
    line = None
    match = rev_re.search(path)
    if match:
        path = match.group(1)
        rev = match.group(2)
        if match.group(3):
            line = int(match.group(3))
    path = urllib.unquote(path)
    return path, rev, line

def get_existing_node(req, repos, path, rev):
    try: 
        return repos.get_node(path, rev) 
    except NoSuchNode, e:
        raise TracError(Markup('%s<br><p>You can <a href="%s">search</a> ' 
                               'in the repository history to see if that path '
                               'existed but was later removed.</p>', e.message,
                               req.href.log(path, rev=rev,
                                            mode='path_history')))

def render_node_property(env, name, value):
    """Renders a node property value to HTML.

    Currently only handle multi-line properties. See also #1601.
    """
    if value and '\n' in value:
        value = Markup(''.join(['<br />%s' % escape(v)
                                for v in value.split('\n')]))
    return value
