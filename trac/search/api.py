# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.core import *


class ISearchSource(Interface):
    """Extension point interface for adding search sources to the search
    system.
    """

    def get_search_filters(req):
        """Return a list of filters that this search source supports.
        
        Each filter must be a `(name, label[, default])` tuple, where `name` is
        the internal name, `label` is a human-readable name for display and
        `default` is an optional boolean for determining whether this filter
        is searchable by default.
        """

    def get_search_results(req, terms, filters):
        """Return a list of search results matching each search term in `terms`.
        
        The `filters` parameters is a list of the enabled filters, each item
        being the name of the tuples returned by `get_search_events`.

        The events returned by this function must be tuples of the form
        `(href, title, date, author, excerpt).`
        """


def search_to_sql(db, columns, terms):
    """Convert a search query into an SQL WHERE clause and corresponding
    parameters.
    
    The result is returned as an `(sql, params)` tuple.
    """
    assert columns and terms

    likes = ['%s %s' % (i, db.like()) for i in columns]
    c = ' OR '.join(likes)
    sql = '(' + ') AND ('.join([c] * len(terms)) + ')'
    args = []
    for t in terms:
        args.extend(['%' + db.like_escape(t) + '%'] * len(columns))
    return sql, tuple(args)

def shorten_result(text='', keywords=[], maxlen=240, fuzz=60):
    if not text:
        text = ''
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
    if excerpt_beg < 0:
        excerpt_beg = 0
    msg = text[excerpt_beg:beg+maxlen]
    if beg > fuzz:
        msg = '... ' + msg
    if beg < len(text)-maxlen:
        msg = msg + ' ...'
    return msg
