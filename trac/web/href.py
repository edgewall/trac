# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

from trac.util.text import unicode_quote, unicode_urlencode


class Href(object):
    """Implements a callable that constructs URLs with the given base. The
    function can be called with any number of positional and keyword
    arguments which then are used to assemble the URL.

    Positional arguments are appended as individual segments to
    the path of the URL:

    >>> href = Href('/trac')
    >>> href('ticket', 540)
    '/trac/ticket/540'
    >>> href('ticket', 540, 'attachment', 'bugfix.patch')
    '/trac/ticket/540/attachment/bugfix.patch'
    >>> href('ticket', '540/attachment/bugfix.patch')
    '/trac/ticket/540/attachment/bugfix.patch'

    If a positional parameter evaluates to None, it will be skipped:

    >>> href('ticket', 540, 'attachment', None)
    '/trac/ticket/540/attachment'

    The first path segment can also be specified by calling an attribute
    of the instance, as follows:

    >>> href.ticket(540)
    '/trac/ticket/540'
    >>> href.changeset(42, format='diff')
    '/trac/changeset/42?format=diff'

    Simply calling the Href object with no arguments will return the base URL:

    >>> href()
    '/trac'

    Keyword arguments are added to the query string, unless the value is None:

    >>> href = Href('/trac')
    >>> href('timeline', format='rss')
    '/trac/timeline?format=rss'
    >>> href('timeline', format=None)
    '/trac/timeline'
    >>> href('search', q='foo bar')
    '/trac/search?q=foo+bar'

    Multiple values for one parameter are specified using a sequence (a list or
    tuple) for the parameter:

    >>> href('timeline', show=['ticket', 'wiki', 'changeset'])
    '/trac/timeline?show=ticket&show=wiki&show=changeset'

    Alternatively, query string parameters can be added by passing a dict or
    list as last positional argument:

    >>> href('timeline', {'from': '02/24/05', 'daysback': 30})
    '/trac/timeline?daysback=30&from=02%2F24%2F05'
    >>> href('timeline', {})
    '/trac/timeline'
    >>> href('timeline', [('from', '02/24/05')])
    '/trac/timeline?from=02%2F24%2F05'
    >>> href('timeline', ()) == href('timeline', []) == href('timeline', {})
    True

    The usual way of quoting arguments that would otherwise be interpreted
    as Python keywords is supported too:

    >>> href('timeline', from_='02/24/05', daysback=30)
    '/trac/timeline?from=02%2F24%2F05&daysback=30'

    If the order of query string parameters should be preserved, you may also
    pass a sequence of (name, value) tuples as last positional argument:

    >>> href('query', (('group', 'component'), ('groupdesc', 1)))
    '/trac/query?group=component&groupdesc=1'

    >>> params = []
    >>> params.append(('group', 'component'))
    >>> params.append(('groupdesc', 1))
    >>> href('query', params)
    '/trac/query?group=component&groupdesc=1'

    By specifying an absolute base, the function returned will also generate
    absolute URLs:

    >>> href = Href('http://trac.edgewall.org')
    >>> href('ticket', 540)
    'http://trac.edgewall.org/ticket/540'

    >>> href = Href('https://trac.edgewall.org')
    >>> href('ticket', 540)
    'https://trac.edgewall.org/ticket/540'

    In common usage, it may improve readability to use the function-calling
    ability for the first component of the URL as mentioned earlier:

    >>> href = Href('/trac')
    >>> href.ticket(540)
    '/trac/ticket/540'
    >>> href.browser('/trunk/README.txt', format='txt')
    '/trac/browser/trunk/README.txt?format=txt'
    
    The path_safe argument specifies the characters that don't need to be
    quoted in the path arguments. Likewise, the query_safe argument specifies
    the characters that don't need to be quoted in the query string:

    >>> href = Href('')
    >>> href.milestone('<look,here>', param='<here,too>')
    '/milestone/%3Clook%2Chere%3E?param=%3Chere%2Ctoo%3E'

    >>> href = Href('', path_safe='/<,', query_safe=',>')
    >>> href.milestone('<look,here>', param='<here,too>')
    '/milestone/<look,here%3E?param=%3Chere,too>'
    """

    def __init__(self, base, path_safe="/!~*'()", query_safe="!~*'()"):
        self.base = base.rstrip('/')
        self.path_safe = path_safe
        self.query_safe = query_safe
        self._derived = {}

    def __call__(self, *args, **kw):
        href = self.base
        params = []

        def add_param(name, value):
            if isinstance(value, (list, tuple)):
                for i in [i for i in value if i is not None]:
                    params.append((name, i))
            elif value is not None:
                params.append((name, value))

        if args:
            lastp = args[-1]
            if isinstance(lastp, dict):
                for k, v in lastp.items():
                    add_param(k, v)
                args = args[:-1]
            elif isinstance(lastp, (list, tuple)):
                for k, v in lastp:
                    add_param(k, v)
                args = args[:-1]

        # build the path
        path = '/'.join(unicode_quote(unicode(arg).strip('/'), self.path_safe)
                        for arg in args if arg is not None)
        if path:
            href += '/' + path
        elif not href:
            href = '/'

        # assemble the query string
        for k, v in kw.items():
            add_param(k.endswith('_') and k[:-1] or k, v)
        if params:
            href += '?' + unicode_urlencode(params, self.query_safe)

        return href

    def __getattr__(self, name):
        if name not in self._derived:
            self._derived[name] = lambda *args, **kw: self(name, *args, **kw)
        return self._derived[name]

    def __add__(self, rhs):
        if rhs.startswith('/'):
            return self.base + rhs
        if rhs:
            return self.base + '/' + rhs
        return self.base or '/'


if __name__ == '__main__':
    import doctest, sys
    doctest.testmod(sys.modules[__name__])
