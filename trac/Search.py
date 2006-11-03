# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
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

import re
import time

from genshi.builder import tag, Element

from trac.config import IntOption
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util.datefmt import format_datetime
from trac.util.presentation import Paginator
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import IWikiSyntaxProvider, wiki_to_link


class ISearchSource(Interface):
    """
    Extension point interface for adding search sources to the Trac
    Search system.
    """

    def get_search_filters(self, req):
        """
        Return a list of filters that this search source supports. Each
        filter must be a (name, label[, default]) tuple, where `name` is the
        internal name, `label` is a human-readable name for display and
        `default` is an optional boolean for determining whether this filter
        is searchable by default.
        """

    def get_search_results(self, req, terms, filters):
        """
        Return a list of search results matching each search term in `terms`.
        The `filters` parameters is a list of the enabled
        filters, each item being the name of the tuples returned by
        `get_search_events`.

        The events returned by this function must be tuples of the form
        (href, title, date, author, excerpt).
        """


def search_terms(q):
    """
    Break apart a search query into its various search terms.  Terms are
    grouped implicitly by word boundary, or explicitly by (single or double)
    quotes.
    """
    results = []
    for term in re.split('(".*?")|(\'.*?\')|(\s+)', q):
        if term != None and term.strip() != '':
            if term[0] == term[-1] == "'" or term[0] == term[-1] == '"':
                term = term[1:-1]
            results.append(term)
    return results

def search_to_sql(db, columns, terms):
    """
    Convert a search query into a SQL condition string and corresponding
    parameters. The result is returned as a (string, params) tuple.
    """
    if len(columns) < 1 or len(terms) < 1:
        raise TracError('Empty search attempt, this should really not happen.')

    likes = ['%s %s' % (i, db.like()) for i in columns]
    c = ' OR '.join(likes)
    sql = '(' + ') AND ('.join([c] * len(terms)) + ')'
    args = []
    for t in terms:
        args.extend(['%'+db.like_escape(t)+'%'] * len(columns))
    return sql, tuple(args)

def shorten_result(text='', keywords=[], maxlen=240, fuzz=60):
    if not text: text = ''
    text_low = text.lower()
    beg = -1
    for k in keywords:
        i = text_low.find(k.lower())
        if (i > -1 and i < beg) or beg == -1:
            beg = i
    excerpt_beg = 0
    if beg > fuzz:
        for sep in ('.', ':', ';', '='):
            eb = text.find(sep, beg - fuzz, beg - 1)
            if eb > -1:
                eb += 1
                break
        else:
            eb = beg - fuzz
        excerpt_beg = eb
    if excerpt_beg < 0: excerpt_beg = 0
    msg = text[excerpt_beg:beg+maxlen]
    if beg > fuzz:
        msg = '... ' + msg
    if beg < len(text)-maxlen:
        msg = msg + ' ...'
    return msg


class SearchModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    search_sources = ExtensionPoint(ISearchSource)
    
    RESULTS_PER_PAGE = 10

    min_query_length = IntOption('search', 'min_query_length', 3,
        """Minimum length of query string allowed when performing a search.""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'search'

    def get_navigation_items(self, req):
        if 'SEARCH_VIEW' in req.perm:
            yield ('mainnav', 'search',
                   tag.a('Search', href=req.href.search(), accesskey=4))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['SEARCH_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/search/?', req.path_info) is not None

    def process_request(self, req):
        req.perm.assert_permission('SEARCH_VIEW')

        available_filters = []
        for source in self.search_sources:
            available_filters += source.get_search_filters(req)
        filters = [f[0] for f in available_filters if req.args.has_key(f[0])]
        if not filters:
            filters = [f[0] for f in available_filters
                       if len(f) < 3 or len(f) > 2 and f[2]]
        data = {'filters': [{'name': f[0], 'label': f[1],
                             'active': f[0] in filters}
                            for f in available_filters]}

        query = req.args.get('q')
        if query:
            data['query'] = query
            data['quickjump'] = self.check_quickjump(req, query)
            if query.startswith('!'):
                query = query[1:]
            terms = search_terms(query)

            # Refuse queries that obviously would result in a huge result set
            if len(terms) == 1 and len(terms[0]) < self.min_query_length:
                raise TracError('Search query too short. '
                                'Query must be at least %d characters long.' % \
                                self.min_query_length, 'Search Error')

            results = []
            for source in self.search_sources:
                results += list(source.get_search_results(req, terms, filters))
            results.sort(lambda x,y: cmp(y[2], x[2]))

            page = int(req.args.get('page', '1'))
            results = Paginator(results, page - 1, self.RESULTS_PER_PAGE)
            for idx, result in enumerate(results):
                results[idx] = {'href': result[0], 'title': result[1],
                                'date': format_datetime(result[2]),
                                'author': result[3], 'excerpt': result[4]}
            data['results'] = results

            if results.has_next_page:
                next_href = req.href.search(zip(filters, ['on'] * len(filters)),
                                            q=req.args.get('q'), page=page + 1,
                                            noquickjump=1)
                add_link(req, 'next', next_href, 'Next Page')

            if results.has_previous_page:
                prev_href = req.href.search(zip(filters, ['on'] * len(filters)),
                                            q=req.args.get('q'), page=page - 1,
                                            noquickjump=1)
                add_link(req, 'prev', prev_href, 'Previous Page')

            data['page_href'] = req.href.search(
                zip(filters, ['on'] * len(filters)), q=req.args.get('q'),
                noquickjump=1)

        add_stylesheet(req, 'common/css/search.css')
        return 'search.html', data, None

    def check_quickjump(self, req, kwd):
        noquickjump = int(req.args.get('noquickjump', '0'))
        # Source quickjump
        quickjump_href = None
        if kwd[0] == '/':
            quickjump_href = req.href.browser(kwd)
            name = kwd
            description = 'Browse repository path ' + kwd
        else:
            link = wiki_to_link(kwd, self.env, req)
            if isinstance(link, Element):
                quickjump_href = link.attrib.get('href')
                name = link.children
                description = link.attrib.get('title', '')
        if quickjump_href:
            if noquickjump:
                return {'href': quickjump_href, 'name': tag.EM(name),
                        'description': description}
            else:
                req.redirect(quickjump_href)

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('search', self._format_link)

    def _format_link(self, formatter, ns, target, label):
        path, query, fragment = formatter.split_link(target)
        if query:
            href = formatter.href.search() + query.replace(' ', '+')
        else:
            href = formatter.href.search(q=path)
        return tag.a(label, class_='search', href=href)
