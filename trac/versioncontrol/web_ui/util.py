# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2007 Christian Boos <cboos@edgewall.org>
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
#         Christian Boos <cboos@edgewall.org>

from itertools import izip
from tempfile import TemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED

from genshi.builder import tag

from trac.resource import ResourceNotFound
from trac.util import content_disposition, create_zipinfo
from trac.util.datefmt import datetime, http_date, utc
from trac.util.translation import tag_, _
from trac.versioncontrol.api import Changeset, NoSuchNode, NoSuchChangeset
from trac.web.api import RequestDone

__all__ = ['get_changes', 'get_path_links', 'get_existing_node',
           'get_allowed_node', 'make_log_graph', 'render_zip']


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
              'href': href.browser(rev=rev if reponame == '' else None,
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
                         href=req.href.log(repos.reponame or None, path,
                                           rev=rev, mode='path_history'))
        raise ResourceNotFound(tag(
            tag.p(e, class_="message"),
            tag.p(tag_("You can %(search)s in the repository history to see "
                       "if that path existed but was later removed",
                       search=search_a))))


def get_allowed_node(repos, path, rev, perm):
    if repos is not None:
        try:
            node = repos.get_node(path, rev)
        except (NoSuchNode, NoSuchChangeset):
            return None
        if node.is_viewable(perm):
            return node


def make_log_graph(repos, revs):
    """Generate graph information for the given revisions.

    Returns a tuple `(threads, vertices, columns)`, where:

     * `threads`: List of paint command lists `[(type, column, line)]`, where
       `type` is either 0 for "move to" or 1 for "line to", and `column` and
       `line` are coordinates.
     * `vertices`: List of `(column, thread_index)` tuples, where the `i`th
       item specifies the column in which to draw the dot in line `i` and the
       corresponding thread.
     * `columns`: Maximum width of the graph.
    """
    threads = []
    vertices = []
    columns = 0
    revs = iter(revs)

    def add_edge(thread, column, line):
        if thread and thread[-1][:2] == [1, column] \
                and thread[-2][1] == column:
            thread[-1][2] = line
        else:
            thread.append([1, column, line])

    try:
        next_rev = revs.next()
        line = 0
        active = []
        active_thread = []
        while True:
            rev = next_rev
            if rev not in active:
                # Insert new head
                threads.append([[0, len(active), line]])
                active_thread.append(threads[-1])
                active.append(rev)

            columns = max(columns, len(active))
            column = active.index(rev)
            vertices.append((column, threads.index(active_thread[column])))

            next_rev = revs.next() # Raises StopIteration when no more revs
            next = active[:]
            parents = list(repos.parent_revs(rev))

            # Replace current item with parents not already present
            new_parents = [p for p in parents if p not in active]
            next[column : column + 1] = new_parents

            # Add edges to parents
            for col, (r, thread) in enumerate(izip(active, active_thread)):
                if r in next:
                    add_edge(thread, next.index(r), line + 1)
                elif r == rev:
                    if new_parents:
                        parents.remove(new_parents[0])
                        parents.append(new_parents[0])
                    for parent in parents:
                        if parent != parents[0]:
                            thread.append([0, col, line])
                        add_edge(thread, next.index(parent), line + 1)

            if not new_parents:
                del active_thread[column]
            else:
                base = len(threads)
                threads.extend([[0, column + 1 + i, line + 1]]
                                for i in xrange(len(new_parents) - 1))
                active_thread[column + 1 : column + 1] = threads[base:]

            active = next
            line += 1
    except StopIteration:
        pass
    return threads, vertices, columns


def render_zip(req, filename, repos, root_node, iter_nodes):
    """Send a ZIP file containing the data corresponding to the `nodes`
    iterable.

    :type root_node: `~trac.versioncontrol.api.Node`
    :param root_node: optional ancestor for all the *nodes*

    :param iter_nodes: callable taking the optional *root_node* as input
                       and generating the `~trac.versioncontrol.api.Node`
                       for which the content should be added into the zip.
    """
    req.send_response(200)
    req.send_header('Content-Type', 'application/zip')
    req.send_header('Content-Disposition',
                    content_disposition('inline', filename))
    if root_node:
        req.send_header('Last-Modified', http_date(root_node.last_modified))
        root_path = root_node.path.rstrip('/')
    else:
        root_path = ''
    if root_path:
        root_path += '/'
        root_name = root_node.name + '/'
    else:
        root_name = ''
    root_len = len(root_path)
    req.end_headers()

    def write_partial(fileobj, start):
        end = fileobj.tell()
        fileobj.seek(start, 0)
        remaining = end - start
        while remaining > 0:
            chunk = fileobj.read(min(remaining, 4096))
            req.write(chunk)
            remaining -= len(chunk)
        fileobj.seek(end, 0)
        return end

    pos = 0
    fileobj = TemporaryFile(prefix='trac-', suffix='.zip')
    try:
        zipfile = ZipFile(fileobj, 'w', ZIP_DEFLATED)
        for node in iter_nodes(root_node):
            if node is root_node:
                continue
            path = node.path.strip('/')
            assert path.startswith(root_path)
            path = root_name + path[root_len:]
            kwargs = {'mtime': node.last_modified}
            data = None
            if node.isfile:
                data = node.get_processed_content(eol_hint='CRLF').read()
                properties = node.get_properties()
                # Subversion specific
                if 'svn:special' in properties and data.startswith('link '):
                    data = data[5:]
                    kwargs['symlink'] = True
                if 'svn:executable' in properties:
                    kwargs['executable'] = True
            elif node.isdir and path:
                kwargs['dir'] = True
                data = ''
            if data is not None:
                zipfile.writestr(create_zipinfo(path, **kwargs), data)
                pos = write_partial(fileobj, pos)
    finally:
        try:
            zipfile.close()
            write_partial(fileobj, pos)
        finally:
            fileobj.close()
    raise RequestDone
