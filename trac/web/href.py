# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

from urllib import quote, urlencode


class Href(object):
    """
    Implements a callable that constructs URLs with the given base. The
    function can be called with any number of positional and keyword
    arguments which than are used to assemble the URL.

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

    >>> href('ticket', 540, 'attachment')
    '/trac/ticket/540/attachment'

    The first path segment can also be specified by calling an attribute
    of the function, as follows:

    >>> href.ticket(540)
    '/trac/ticket/540'
    >>> href.changeset(42, format='diff')
    '/trac/changeset/42?format=diff'

    Keyword arguments are added to the query string, unless the value is None:

    >>> href = Href('/trac')
    >>> href('timeline', format='rss')
    '/trac/timeline?format=rss'
    >>> href('timeline', format=None)
    '/trac/timeline'

    Multiple values for one parameter are specified using a sequence (a list or
    tuple) for the parameter:

    >>> href('timeline', show=['ticket', 'wiki', 'changeset'])
    '/trac/timeline?show=ticket&show=wiki&show=changeset'

    Alternatively, query string parameters can be added by passing a dict or
    list as last positional argument:

    >>> href('timeline', {'from': '02/24/05', 'daysback': 30})
    '/trac/timeline?daysback=30&from=02%2F24%2F05'

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

    >>> href = Href('http://projects.edgewall.com/trac')
    >>> href('ticket', 540)
    'http://projects.edgewall.com/trac/ticket/540'

    >>> href = Href('https://projects.edgewall.com/trac')
    >>> href('ticket', 540)
    'https://projects.edgewall.com/trac/ticket/540'

    Finally, the first path segment of the URL to generate can be specified in
    the following way, mainly to improve readability:

    >>> href = Href('/trac')
    >>> href.ticket(540)
    '/trac/ticket/540'
    >>> href.browser('/trunk/README.txt', format='txt')
    '/trac/browser/trunk/README.txt?format=txt'
    """

    def __init__(self, base):
        self.base = base
        self._derived = {}

    def __call__(self, *args, **kw):
        href = self.base
        if href and href[-1] == '/':
            href = href[:-1]
        params = []

        def add_param(name, value):
            if type(value) in (list, tuple):
                for i in [i for i in value if i != None]:
                    params.append((name, i))
            elif v != None:
                params.append((name, value))

        lastp = args[-1]
        if lastp and type(lastp) is dict:
            for k,v in lastp.items():
                add_param(k, v)
            args = args[:-1]
        elif lastp and type(lastp) in (list, tuple):
            for k,v in lastp:
                add_param(k, v)
            args = args[:-1]

        # build the path
        path = '/'.join([quote(str(arg).strip('/')) for arg in args
                         if arg != None])
        if path:
            href += '/' + path

        # assemble the query string
        for k,v in kw.items():
            add_param(k, v)

        if params:
            href += '?' + urlencode(params)

        return href

    def __getattr__(self, name):
        if not name in self._derived.keys():
            self._derived[name] = lambda *args, **kw: self(name, *args, **kw)
        return self._derived[name]


def _test():
    import doctest
    doctest.testmod()

if __name__ == '__main__':
    _test()
