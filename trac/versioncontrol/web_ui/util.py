# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2007 Christian Boos <cboos@neuf.fr>
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
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christian Boos <cboos@neuf.fr>

import re
import urllib

from genshi.builder import tag

from trac.core import TracError
from trac.resource import ResourceNotFound 
from trac.util.datefmt import pretty_timedelta
from trac.util.text import shorten_line
from trac.versioncontrol.api import NoSuchNode, NoSuchChangeset

__all__ = ['get_changes', 'get_path_links', 'get_existing_node']

def get_changes(repos, revs):
    changes = {}
    for rev in revs:
        if rev in changes:
            continue
        try:
            changeset = repos.get_changeset(rev)
        except NoSuchChangeset:
            changeset = {}
        changes[rev] = changeset
    return changes

def get_path_links(href, fullpath, rev, order=None, desc=None):
    links = [{'name': 'root',
              'href': href.browser(rev=rev, order=order, desc=desc)}]
    path = ''
    for part in [p for p in fullpath.split('/') if p]:
        path += part + '/'
        links.append({
            'name': part,
            'href': href.browser(path, rev=rev, order=order, desc=desc)
            })
    return links

def get_existing_node(req, repos, path, rev):
    try: 
        return repos.get_node(path, rev) 
    except NoSuchNode, e:
        raise ResourceNotFound(tag(
            tag.p(e.message, class_="message"), 
            tag.p("You can ",
                  tag.a("search",
                        href=req.href.log(path, rev=rev, mode='path_history')),
                  " in the repository history to see if that path existed but"
                  " was later removed")))
