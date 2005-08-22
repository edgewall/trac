# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
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

from __future__ import generators
import re
import time

from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util import TracError, escape, shorten_line
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

    def get_search_results(self, req, query, filters):
        """
        Return a list of search results matching `query`. The `filters`
        parameters is a list of the enabled
        filters, each item being the name of the tuples returned by
        `get_search_events`.

        The events returned by this function must be tuples of the form
        (href, title, date, author, excerpt).
        """


def query_to_sql(db, q, name):
    if q[0] == q[-1] == "'" or q[0] == q[-1] == '"':
        sql_q = "%s %s '%%%s%%'" % (name, db.like(),
                                        q[1:-1].replace("'''", "''"))
    else:
        q = q.replace('\'', '\'\'')
        keywords = q.split(' ')
        x = map(lambda x, name=name: name + ' ' + db.like() +
                '\'%' + x + '%\'', keywords)
        sql_q = ' AND '.join(x)
    return sql_q

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
        yield 'mainnav', 'search', '<a href="%s" accesskey="4">Search</a>' \
              % (self.env.href.search())

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

        if 'q' in req.args:
            query = orig_query = req.args.get('q')
            page = int(req.args.get('page', '1'))
            redir = self.quickjump(query)
            if redir:
                req.redirect(redir)
            elif query.startswith('!'):
                query = query[1:]
            # Refuse queries that obviously would result in a huge result set
            if len(query) < 3 and len(query.split()) == 1:
                raise TracError('Search query too short. '
                                'Query must be at least 3 characters long.',
                                'Search Error')
            results = []
            for source in self.search_sources:
                results += list(source.get_search_results(req, query, filters))
            results.sort(lambda x,y: cmp(y[2], x[2]))
            page_size = self.RESULTS_PER_PAGE
            n = len(results)
            n_pages = n / page_size + 1
            results = results[(page-1) * page_size: page * page_size]

            req.hdf['title'] = 'Search Results'
            req.hdf['search.q'] = orig_query.replace('"', "&#34;")
            req.hdf['search.page'] = page
            req.hdf['search.n_hits'] = n
            req.hdf['search.n_pages'] = n_pages
            req.hdf['search.page_size'] = page_size
            if page < n_pages:
                req.hdf['chrome.links.next'] = [
                    {'title': 'Next Page',
                     'href': self.env.href.search(zip(filters,
                                                      ['on'] * len(filters)),
                                                  q=query, page=page+1)
                    }]
            if page > 1:
                req.hdf['chrome.links.prev'] = [
                    {'title': 'Previous Page',
                     'href': self.env.href.search(zip(filters,
                                                      ['on'] * len(filters)),
                                                  q=query, page=page-1)
                    }]
            req.hdf['search.page_href'] = \
                 self.env.href.search(zip(filters,
                                          ['on'] * len(filters)), q=query)
            req.hdf['search.result'] = [
                { 'href': result[0],
                  'title': result[1],
                  'date': time.strftime('%c', time.localtime(result[2])),
                  'author': result[3],
                  'excerpt': result[4]
                } for result in results]

        add_stylesheet(req, 'css/search.css')
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
        elif kwd[0:len('source:')] == 'source:':
            return self.env.href.browser(kwd[len('source:'):])
        # Wiki quickjump
        elif kwd[0:len('wiki:')] == 'wiki:':
            r = "((^|(?<=[^A-Za-z]))[!]?[A-Z][a-z/]+(?:[A-Z][a-z/]+)+)"
            if re.match (r, kwd[len('wiki:'):]):
                return self.env.href.wiki(kwd[len('wiki:'):])
        elif kwd[0].isupper() and kwd[1].islower():
            r = "((^|(?<=[^A-Za-z]))[!]?[A-Z][a-z/]+(?:[A-Z][a-z/]+)+)"
            if re.match (r, kwd):
                return self.env.href.wiki(kwd)

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('search', self._format_link)

    def _format_link(self, formatter, ns, query, label):
        return '<a class="search" href="%s">%s</a>' \
               % (formatter.href.search(q=query), label)

