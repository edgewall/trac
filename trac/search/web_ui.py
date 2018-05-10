# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
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

import pkg_resources
import re

from trac.config import IntOption, ListOption
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.search.api import ISearchSource
from trac.util.datefmt import format_datetime, user_time
from trac.util.html import Markup, escape, find_element, tag
from trac.util.presentation import Paginator
from trac.util.text import quote_query_string
from trac.util.translation import _
from trac.web.api import IRequestHandler
from trac.web.chrome import (INavigationContributor, ITemplateProvider,
                             accesskey, add_link, add_notice, add_stylesheet,
                             add_warning, web_context)
from trac.wiki.api import IWikiSyntaxProvider
from trac.wiki.formatter import extract_link


class SearchModule(Component):
    """Controller for the search sub-system"""

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITemplateProvider, IWikiSyntaxProvider)

    search_sources = ExtensionPoint(ISearchSource)

    RESULTS_PER_PAGE = 10

    min_query_length = IntOption('search', 'min_query_length', 3,
        """Minimum length of query string allowed when performing a search.
        """)

    default_disabled_filters = ListOption('search',
                                          'default_disabled_filters',
        doc="""Specifies which search filters should be disabled by
               default on the search page. This will also restrict the
               filters for the quick search function. The filter names
               defined by default components are: `wiki`, `ticket`,
               `milestone` and `changeset`.  For plugins, look for
               their implementation of the ISearchSource interface, in
               the `get_search_filters()` method, the first member of
               returned tuple. Once disabled, search filters can still
               be manually enabled by the user on the search page.
               """)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'search'

    def get_navigation_items(self, req):
        if 'SEARCH_VIEW' in req.perm:
            yield ('mainnav', 'search',
                   tag.a(_('Search'), href=req.href.search(),
                         accesskey=accesskey(req, 4)))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['SEARCH_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/search(?:/opensearch)?$', req.path_info) \
               is not None

    def process_request(self, req):
        req.perm.assert_permission('SEARCH_VIEW')

        if req.path_info == '/search/opensearch':
            return ('opensearch.xml', {},
                    {'content_type': 'application/opensearchdescription+xml'})

        query = req.args.get('q')
        available_filters = []
        for source in self.search_sources:
            available_filters.extend(source.get_search_filters(req) or [])
        available_filters.sort(key=lambda f: f[1].lower())

        filters = self._get_selected_filters(req, available_filters)
        data = self._prepare_data(req, query, available_filters, filters)
        if query:
            noquickjump = req.args.getbool('noquickjump', False)
            data['quickjump'] = self._check_quickjump(req, noquickjump, query)
            if query.startswith('!'):
                query = query[1:]

            terms = self._parse_query(req, query)
            if terms:
                results = self._do_search(req, terms, filters)
                if results:
                    data.update(self._prepare_results(req, filters, results))
            if noquickjump and filters:
                req.session['search.filters'] = ','.join(filters)

        add_stylesheet(req, 'common/css/search.css')
        return 'search.html', data

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.search', 'templates')]

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('search', self._format_link)

    def _format_link(self, formatter, ns, target, label):
        path, query, fragment = formatter.split_link(target)
        if path:
            href = formatter.href.search(q=path)
            if query:
                href += '&' + quote_query_string(query[1:])
        else:
            href = formatter.href.search() + quote_query_string(query)
        href += fragment
        return tag.a(label, class_='search', href=href)

    # IRequestHandler helper methods

    def _get_selected_filters(self, req, available_filters):
        """Return selected filters or the default filters if none was
        selected.
        """
        filters = [f[0] for f in available_filters if f[0] in req.args]
        if not filters:
            session_filters = req.session.get('search.filters')
            if session_filters:
                available_filters_dict = dict([f[0:2]
                                               for f in available_filters])
                filters = [f for f in session_filters.split(',')
                           if f in available_filters_dict]
            else:
                filters = [f[0] for f in available_filters
                           if f[0] not in self.default_disabled_filters and
                           (len(f) < 3 or len(f) > 2 and f[2])]
        return filters

    def _prepare_data(self, req, query, available_filters, filters):
        return {'filters': [{'name': f[0], 'label': f[1],
                             'active': f[0] in filters}
                            for f in available_filters],
                'query': query, 'quickjump': None, 'results': []}

    def _check_quickjump(self, req, noquickjump, kwd):
        """Look for search shortcuts"""
        # Source quickjump  FIXME: delegate to ISearchSource.search_quickjump
        quickjump_href = None
        if kwd[0] == '/':
            quickjump_href = req.href.browser(kwd)
            name = kwd
            description = _('Browse repository path %(path)s', path=kwd)
        else:
            context = web_context(req, 'search')
            link = find_element(extract_link(self.env, context, kwd), 'href')
            if link is not None:
                quickjump_href = link.attrib.get('href')
                name = link.children
                description = link.attrib.get('title', '')
        if quickjump_href:
            # Only automatically redirect to local quickjump links
            if not quickjump_href.startswith(req.base_path or '/'):
                noquickjump = True
            if noquickjump:
                return {'href': quickjump_href, 'name': tag.em(name),
                        'description': description}
            else:
                help_url = req.href.wiki('TracSearch') + '#Quicksearches'
                search_url = req.href.search(q=kwd, noquickjump=1)
                # FIXME: use tag_
                add_notice(req, Markup(_(
                    'You arrived here through the <a href="%(help_url)s">'
                    'quick-jump</a> search feature. To instead search for the '
                    'term <strong>%(term)s</strong>, click <a '
                    'href="%(search_url)s">here</a>.',
                    help_url=escape(help_url), term=escape(kwd),
                    search_url=escape(search_url))))
                req.redirect(quickjump_href)

    def _get_search_terms(self, query):
        """Break apart a search query into its various search terms.

        Terms are grouped implicitly by word boundary, or explicitly by (single
        or double) quotes.
        """
        terms = []
        for term in re.split('(".*?")|(\'.*?\')|(\s+)', query):
            if term is not None and term.strip():
                if term[0] == term[-1] and term[0] in "'\"":
                    term = term[1:-1]
                terms.append(term)
        return terms

    def _parse_query(self, req, query):
        """Parse query and refuse those which would result in a huge result set
        """
        terms = self._get_search_terms(query)
        if terms and (len(terms) > 1 or
                      len(terms[0]) >= self.min_query_length):
            return terms

        add_warning(req, _('Search query too short. '
                           'Query must be at least %(num)s characters long.',
                           num=self.min_query_length))

    def _do_search(self, req, terms, filters):
        results = []
        for source in self.search_sources:
            results.extend(source.get_search_results(req, terms, filters)
                           or [])
        # backwarts compatibility: add empty order parameter if none is included
        results = [x if len(x) == 6 else x + (0, 0, 0, 0) for x in results]
        # sort by order parameter
        sortedresults = sorted(results, key=lambda x: x[5], reverse=True)
        # remove order parameter
        return [(href, title, date, author, excerpt) for (href, title, date, author, excerpt, order) in sortedresults]

    def _prepare_results(self, req, filters, results):
        page = req.args.getint('page', 1, min=1)
        try:
            results = Paginator(results, page - 1, self.RESULTS_PER_PAGE)
        except TracError:
            add_warning(req, _("Page %(page)s is out of range.", page=page))
            page = 1
            results = Paginator(results, page - 1, self.RESULTS_PER_PAGE)

        for idx, result in enumerate(results):
            results[idx] = {'href': result[0], 'title': result[1],
                            'date': user_time(req, format_datetime, result[2]),
                            'author': result[3], 'excerpt': result[4]}

        pagedata = []
        shown_pages = results.get_shown_pages(21)
        for shown_page in shown_pages:
            page_href = req.href.search([(f, 'on') for f in filters],
                                        q=req.args.get('q'),
                                        page=shown_page, noquickjump=1)
            pagedata.append([page_href, None, str(shown_page),
                             _("Page %(num)d", num=shown_page)])

        fields = ['href', 'class', 'string', 'title']
        results.shown_pages = [dict(zip(fields, p)) for p in pagedata]

        results.current_page = {'href': None, 'class': 'current',
                                'string': str(results.page + 1),
                                'title': None}

        if results.has_next_page:
            next_href = req.href.search(zip(filters, ['on'] * len(filters)),
                                        q=req.args.get('q'), page=page + 1,
                                        noquickjump=1)
            add_link(req, 'next', next_href, _('Next Page'))

        if results.has_previous_page:
            prev_href = req.href.search(zip(filters, ['on'] * len(filters)),
                                        q=req.args.get('q'), page=page - 1,
                                        noquickjump=1)
            add_link(req, 'prev', prev_href, _('Previous Page'))

        page_href = req.href.search(
            zip(filters, ['on'] * len(filters)), q=req.args.get('q'),
            noquickjump=1)
        return {'results': results, 'page_href': page_href}
