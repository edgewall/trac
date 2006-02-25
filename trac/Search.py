# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2003-2004 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import re
import time

from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util import TracError, escape, format_datetime, Markup
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import IWikiSyntaxProvider


class ISearchSource(Interface):
    """
    Extension point interface for adding search sources to the Trac
    Search system.
    """

    def get_search_filters(self, req):
        """
        Return a list of filters that this search source supports. Each
        filter must be a (name, label) tuple, where `name` is the internal
        name, and `label` is a human-readable name for display.
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

    likes = [r"%s %s %%s ESCAPE '_'" % (i, db.like()) for i in columns]
    c = ' OR '.join(likes)
    sql = '(' + ') AND ('.join([c] * len(terms)) + ')'
    args = []
    escape_re = re.compile(r'([_%])')
    for t in terms:
        t = escape_re.sub(r'_\1', t) # escape LIKE syntax
        args.extend(['%'+t+'%'] * len(columns)) 
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

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'search'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('SEARCH_VIEW'):
            return
        yield ('mainnav', 'search',
               Markup('<a href="%s" accesskey="4">Search</a>',
                      self.env.href.search()))

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
            filters = [f[0] for f in available_filters]
                
        req.hdf['search.filters'] = [
            { 'name': filter[0],
              'label': filter[1],
              'active': filter[0] in filters
            } for filter in available_filters]
                
        req.hdf['title'] = 'Search'

        query = req.args.get('q')
        if query:
            page = int(req.args.get('page', '1'))
            redir = self.quickjump(query)
            if redir:
                req.redirect(redir)
            elif query.startswith('!'):
                query = query[1:]
            terms = search_terms(query)
            # Refuse queries that obviously would result in a huge result set
            if len(terms) == 1 and len(terms[0]) < 3:
                raise TracError('Search query too short. '
                                'Query must be at least 3 characters long.',
                                'Search Error')
            results = []
            for source in self.search_sources:
                results += list(source.get_search_results(req, terms, filters))
            results.sort(lambda x,y: cmp(y[2], x[2]))
            page_size = self.RESULTS_PER_PAGE
            n = len(results)
            n_pages = n / page_size + 1
            results = results[(page-1) * page_size: page * page_size]

            req.hdf['title'] = 'Search Results'
            req.hdf['search.q'] = req.args.get('q')
            req.hdf['search.page'] = page
            req.hdf['search.n_hits'] = n
            req.hdf['search.n_pages'] = n_pages
            req.hdf['search.page_size'] = page_size
            if page < n_pages:
                next_href = self.env.href.search(zip(filters,
                                                     ['on'] * len(filters)),
                                                 q=req.args.get('q'),
                                                 page=page + 1)
                add_link(req, 'next', next_href, 'Next Page')
            if page > 1:
                prev_href = self.env.href.search(zip(filters,
                                                     ['on'] * len(filters)),
                                                 q=req.args.get('q'),
                                                 page=page - 1)
                add_link(req, 'prev', prev_href, 'Previous Page')
            req.hdf['search.page_href'] = self.env.href.search(zip(filters,
                                                                   ['on'] * len(filters)),
                                                               q=req.args.get('q'))
            req.hdf['search.result'] = [
                { 'href': result[0],
                  'title': result[1],
                  'date': format_datetime(result[2]),
                  'author': result[3],
                  'excerpt': result[4]
                } for result in results]

        add_stylesheet(req, 'common/css/search.css')
        return 'search.cs', None

    def quickjump(self, kwd):
        if len(kwd.split()) != 1:
            return None
        # Ticket quickjump
        if kwd[0] == '#' and kwd[1:].isdigit():
            return self.env.href.ticket(kwd[1:])
        elif kwd[0:len('ticket:')] == 'ticket:' and kwd[len('ticket:'):].isdigit():
            return self.env.href.ticket(kwd[len('ticket:'):])
        elif kwd[0:len('bug:')] == 'bug:' and kwd[len('bug:'):].isdigit():
            return self.env.href.ticket(kwd[len('bug:'):])
        # Changeset quickjump
        elif kwd[0] == '[' and kwd[-1] == ']' and kwd[1:-1].isdigit():
            return self.env.href.changeset(kwd[1:-1])
        elif kwd[0:len('changeset:')] == 'changeset:' and kwd[len('changeset:'):].isdigit():
            return self.env.href.changeset(kwd[len('changeset:'):])
        # Report quickjump
        elif kwd[0] == '{' and kwd[-1] == '}' and kwd[1:-1].isdigit():
            return self.env.href.report(kwd[1:-1])
        elif kwd[0:len('report:')] == 'report:' and kwd[len('report:'):].isdigit():
            return self.env.href.report(kwd[len('report:'):])
        # Milestone quickjump
        elif kwd[0:len('milestone:')] == 'milestone:':
            return self.env.href.milestone(kwd[len('milestone:'):])
        # Source quickjump
        elif kwd[0] == '/':
            return self.env.href.browser(kwd)
        elif kwd[0:len('source:')] == 'source:':
            return self.env.href.browser(kwd[len('source:'):])
        # Wiki quickjump
        elif kwd[0:len('wiki:')] == 'wiki:':
            r = "((^|(?<=[^A-Za-z]))[!]?[A-Z][a-z/]+(?:[A-Z][a-z/]+)+)"
            if re.match (r, kwd[len('wiki:'):]):
                return self.env.href.wiki(kwd[len('wiki:'):])
        elif len(kwd) > 1 and kwd[0].isupper() and kwd[1].islower():
            r = "((^|(?<=[^A-Za-z]))[!]?[A-Z][a-z/]+(?:[A-Z][a-z/]+)+)"
            if re.match (r, kwd):
                return self.env.href.wiki(kwd)

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('search', self._format_link)

    def _format_link(self, formatter, ns, query, label):
        if query and query[0] == '?':
            href = formatter.href.search() + query.replace(' ', '+')
        else:
            href = formatter.href.search(q=query)
        return '<a class="search" href="%s">%s</a>' % (escape(href), label)

