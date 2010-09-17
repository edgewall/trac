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

from genshi.builder import tag

from trac.resource import ResourceNotFound 
from trac.util.datefmt import datetime, utc
from trac.util.translation import tag_, _
from trac.versioncontrol.api import Changeset, NoSuchNode, NoSuchChangeset

__all__ = ['get_changes', 'get_path_links', 'get_existing_node']

def get_changes(repos, revs, log=None):
    changes = {}
    for rev in revs:
        if rev in changes:
            continue
        try:
            changeset = repos.get_changeset(rev)
        except NoSuchChangeset:
            changeset = Changeset(repos, rev, '', '',
                                  datetime(1970, 1, 1, tzinfo=utc))
            if log is not None:
                log.warning("Unable to get changeset [%s]", rev)
        changes[rev] = changeset
    return changes

def get_path_links(href, reponame, path, rev, order=None, desc=None):
    desc = desc or None
    links = [{'name': 'source:',
              'href': href.browser(rev=reponame == '' and rev or None,
                                   order=order, desc=desc)}]
    if reponame:
        links.append({
            'name': reponame, 
            'href': href.browser(reponame, rev=rev, order=order, desc=desc)})
    partial_path = ''
    for part in [p for p in path.split('/') if p]:
        partial_path += part + '/'
        links.append({
            'name': part,
            'href': href.browser(reponame or None, partial_path, rev=rev,
                                 order=order, desc=desc)
            })
    return links

def get_existing_node(req, repos, path, rev):
    try: 
        return repos.get_node(path, rev) 
    except NoSuchNode, e:
        # TRANSLATOR: You can 'search' in the repository history... (link)
        search_a = tag.a(_("search"), 
                         href=req.href.log(path, rev=rev, mode='path_history'))
        raise ResourceNotFound(tag(
            tag.p(e.message, class_="message"), 
            tag.p(tag_("You can %(search)s in the repository history to see "
                       "if that path existed but was later removed",
                       search=search_a))))
