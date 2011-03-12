# -*- coding: utf-8 -*-
#
# Copyright (C)2006-2009 Edgewall Software
# Copyright (C) 2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""Various utility functions and classes that support common presentation
tasks such as grouping or pagination.
"""

from math import ceil
import re

__all__ = ['classes', 'first_last', 'group', 'istext', 'prepared_paginate', 
           'paginate', 'Paginator']


def classes(*args, **kwargs):
    """Helper function for dynamically assembling a list of CSS class names
    in templates.
    
    Any positional arguments are added to the list of class names. All
    positional arguments must be strings:
    
    >>> classes('foo', 'bar')
    u'foo bar'
    
    In addition, the names of any supplied keyword arguments are added if they
    have a truth value:
    
    >>> classes('foo', bar=True)
    u'foo bar'
    >>> classes('foo', bar=False)
    u'foo'
    
    If none of the arguments are added to the list, this function returns
    `None`:
    
    >>> classes(bar=False)
    """
    classes = list(filter(None, args)) + [k for k, v in kwargs.items() if v]
    if not classes:
        return None
    return u' '.join(classes)

def first_last(idx, seq):
    return classes(first=idx == 0, last=idx == len(seq) - 1)


def group(iterable, num, predicate=None):
    """Combines the elements produced by the given iterable so that every `n`
    items are returned as a tuple.
    
    >>> items = [1, 2, 3, 4]
    >>> for item in group(items, 2):
    ...     print item
    (1, 2)
    (3, 4)
    
    The last tuple is padded with `None` values if its' length is smaller than
    `num`.
    
    >>> items = [1, 2, 3, 4, 5]
    >>> for item in group(items, 2):
    ...     print item
    (1, 2)
    (3, 4)
    (5, None)
    
    The optional `predicate` parameter can be used to flag elements that should
    not be packed together with other items. Only those elements where the
    predicate function returns True are grouped with other elements, otherwise
    they are returned as a tuple of length 1:
    
    >>> items = [1, 2, 3, 4]
    >>> for item in group(items, 2, lambda x: x != 3):
    ...     print item
    (1, 2)
    (3,)
    (4, None)
    """
    buf = []
    for item in iterable:
        flush = predicate and not predicate(item)
        if buf and flush:
            buf += [None] * (num - len(buf))
            yield tuple(buf)
            del buf[:]
        buf.append(item)
        if flush or len(buf) == num:
            yield tuple(buf)
            del buf[:]
    if buf:
        buf += [None] * (num - len(buf))
        yield tuple(buf)


def istext(text):
    from genshi.core import Markup
    return isinstance(text, basestring) and not isinstance(text, Markup)

def prepared_paginate(items, num_items, max_per_page):
    if max_per_page == 0:
        num_pages = 1
    else:
        num_pages = int(ceil(float(num_items) / max_per_page))
    return items, num_items, num_pages

def paginate(items, page=0, max_per_page=10):
    """Simple generic pagination.
    
    Given an iterable, this function returns:
     * the slice of objects on the requested page,
     * the total number of items, and
     * the total number of pages.
    
    The `items` parameter can be a list, tuple, or iterator:
    
    >>> items = range(12)
    >>> items
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    >>> paginate(items)
    ([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 12, 2)
    >>> paginate(items, page=1)
    ([10, 11], 12, 2)
    >>> paginate(iter(items))
    ([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 12, 2)
    >>> paginate(iter(items), page=1)
    ([10, 11], 12, 2)
    
    This function also works with generators:
    
    >>> def generate():
    ...     for idx in range(12):
    ...         yield idx
    >>> paginate(generate())
    ([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 12, 2)
    >>> paginate(generate(), page=1)
    ([10, 11], 12, 2)
    
    The `max_per_page` parameter can be used to set the number of items that
    should be displayed per page:
    
    >>> items = range(12)
    >>> paginate(items, page=0, max_per_page=6)
    ([0, 1, 2, 3, 4, 5], 12, 2)
    >>> paginate(items, page=1, max_per_page=6)
    ([6, 7, 8, 9, 10, 11], 12, 2)
    """
    if not page:
        page = 0
    start = page * max_per_page
    stop = start + max_per_page

    count = None
    if hasattr(items, '__len__'):
        count = len(items)
        if count:
            assert start < count, 'Page %d out of range' % page

    try: # Try slicing first for better performance
        retval = items[start:stop]
    except TypeError: # Slicing not supported, so iterate through the whole list
        retval = []
        idx = -1 # Needed if items = []
        for idx, item in enumerate(items):
            if start <= idx < stop:
                retval.append(item)
            # If we already obtained the total number of items via `len()`,
            # we can break out of the loop as soon as we've got the last item
            # for the requested page
            if count is not None and idx >= stop:
                break
        if count is None:
            count = idx + 1

    return retval, count, int(ceil(float(count) / max_per_page))


class Paginator(object):

    def __init__(self, items, page=0, max_per_page=10, num_items=None):
        if not page:
            page = 0

        if num_items is None:
            items, num_items, num_pages = paginate(items, page, max_per_page)
        else:
            items, num_items, num_pages = prepared_paginate(items, num_items,
                                                            max_per_page)
        offset = page * max_per_page        
        self.page = page
        self.max_per_page = max_per_page
        self.items = items
        self.num_items = num_items
        self.num_pages = num_pages
        self.span = offset, offset + len(items)
        self.show_index = True

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def __nonzero__(self):
        return len(self.items) > 0

    def __setitem__(self, idx, value):
        self.items[idx] = value

    @property
    def has_more_pages(self):
        return self.num_pages > 1

    @property
    def has_next_page(self):
        return self.page + 1 < self.num_pages

    @property
    def has_previous_page(self):
        return self.page > 0
   
    def get_shown_pages(self, page_index_count = 11):
        if self.has_more_pages == False:
            return range(1, 2)

        min_page = 1
        max_page = int(ceil(float(self.num_items) / self.max_per_page))
        current_page = self.page + 1
        start_page = current_page - page_index_count / 2
        end_page = current_page + page_index_count / 2 + \
                   (page_index_count % 2 - 1)

        if start_page < min_page:
            start_page = min_page
        if end_page > max_page:
            end_page = max_page

        return range(start_page, end_page + 1)

    def displayed_items(self):
        from trac.util.translation import _
        start, stop = self.span
        total = self.num_items
        if start+1 == stop:
            return _("%(last)d of %(total)d", last=stop, total=total)
        else:
            return _("%(start)d - %(stop)d of %(total)d",
                    start=self.span[0]+1, stop=self.span[1], total=total)


def separated(items, sep=','):
    """Yield `(item, sep)` tuples, one for each element in `items`.

    `sep` will be `None` for the last item.

    >>> list(separated([1, 2]))
    [(1, ','), (2, None)]

    >>> list(separated([1]))
    [(1, None)]

    >>> list(separated("abc", ':'))
    [('a', ':'), ('b', ':'), ('c', None)]
    """
    items = iter(items)
    last = items.next()
    for i in items:
        yield last, sep
        last = i
    yield last, None


try:
    from json import dumps

    _js_quote = dict((c, '\\u%04x' % ord(c)) for c in '&<>')
    _js_quote_re = re.compile('[' + ''.join(_js_quote) + ']')
    
    def to_json(value):
        """Encode `value` to JSON."""
        def replace(match):
            return _js_quote[match.group(0)]
        text = dumps(value, sort_keys=True, separators=(',', ':'))
        return _js_quote_re.sub(replace, text)

except ImportError:
    from trac.util.text import javascript_quote
    
    def to_json(value):
        """Encode `value` to JSON."""
        if isinstance(value, basestring):
            return '"%s"' % javascript_quote(value)
        elif value is None:
            return 'null'
        elif value is False:
            return 'false'
        elif value is True:
            return 'true'
        elif isinstance(value, (int, long)):
            return str(value)
        elif isinstance(value, float):
            return repr(value)
        elif isinstance(value, (list, tuple)):
            return '[%s]' % ','.join(to_json(each) for each in value)
        elif isinstance(value, dict):
            return '{%s}' % ','.join('%s:%s' % (to_json(k), to_json(v))
                                     for k, v in sorted(value.iteritems()))
        else:
            raise TypeError('Cannot encode type %s' % value.__class__.__name__)
