# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2019 Edgewall Software
# Copyright (C) 2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

"""Various utility functions and classes that support common presentation
tasks such as grouping or pagination.
"""

from json import JSONEncoder
from datetime import datetime
from math import ceil
import re

from jinja2 import Markup, Undefined, contextfilter, evalcontextfilter
from jinja2.filters import make_attrgetter
from jinja2.utils import soft_unicode

from trac.core import TracError
from .datefmt import to_utimestamp, utc
from .html import Fragment, classes, html_attribute, styles, tag
from .text import javascript_quote

__all__ = ['captioned_button', 'classes', 'first_last', 'group', 'istext',
           'prepared_paginate', 'paginate', 'Paginator']
__no_apidoc__ = 'prepared_paginate'


def jinja2_update(jenv):
    """Augment a Jinja2 environment with filters, tests and global functions
    defined in this module.

    """
    jenv.filters.update(
        flatten=flatten_filter,
        groupattr=groupattr_filter,
        htmlattr=htmlattr_filter,
        max=max_filter,
        mix=min_filter,
        trim=trim_filter,
    )
    jenv.tests.update(
        greaterthan=is_greaterthan,
        greaterthanorequal=is_greaterthanorequal,
        lessthan=is_lessthan,
        lessthanorequal=is_lessthanorequal,
        not_equalto=is_not_equalto,
        not_in=is_not_in,
        text=istext,
    )
    jenv.globals.update(
        classes=classes,
        first_last=first_last,
        group=group,
        istext=istext,
        paginate=paginate,
        separated=separated,
        styles=styles,
        tag=tag,
        to_json=to_json,
    )


# -- Jinja2 custom filters

@evalcontextfilter
def htmlattr_filter(_eval_ctx, d, autospace=True):
    """Create an SGML/XML attribute string based on the items in a dict.

    If the dict itself is `none` or `undefined`, it returns the empty
    string. ``d`` can also be an iterable or a mapping, in which case
    it will be converted to a ``dict``.

    All values that are neither `none` nor `undefined` are
    automatically escaped.

    For HTML attributes like `'checked'` and `'selected'`, a truth
    value will be converted to the key value itself. For others it
    will be `'true'` or `'on'`. For `'class'`, the `classes`
    processing will be applied.

    Example:

    .. sourcecode:: html+jinja

        <ul${{'class': {'my': 1, 'list': True, 'empty': False},
              'missing': none, 'checked': 1, 'selected': False,
              'autocomplete': True, 'id': 'list-%d'|format(variable),
              'style': {'border-radius': '3px' if rounded,
                        'background': '#f7f7f7'}
             }|htmlattr}>
        ...
        </ul>

    Results in something like this:

    .. sourcecode:: html

        <ul class="my list" id="list-42" checked="checked" autocomplete="on"
            style="border-radius: 3px; background: #f7f7f7">
        ...
        </ul>

    As you can see it automatically prepends a space in front of the item
    if the filter returned something unless the second parameter is false.

    Adapted from Jinja2's builtin ``do_xmlattr`` filter.

    """
    if not d:
        return ''
    d = d if isinstance(d, dict) else dict(d)
    # Note: at some point, switch to
    #       https://www.w3.org/TR/html-markup/syntax.html#syntax-attr-empty
    attrs = []
    for key in sorted(d):
        val = d[key]
        val = html_attribute(key, None if isinstance(val, Undefined) else val)
        if val is not None :
            attrs.append(u'%s="%s"' % (key, val))
    rv = u' '.join(attrs)
    if autospace and rv:
        rv = u' ' + rv
    if _eval_ctx.autoescape:
        rv = Markup(rv)
    return rv


def max_filter(seq, default=None):
    """Returns the max value from the sequence."""
    if len(seq):
        return max(seq)
    return default

def min_filter(seq, default=None):
    """Returns the min value from the sequence."""
    if len(seq):
        return min(seq)
    return default


def trim_filter(value, what=None):
    """Strip leading and trailing whitespace or other specified character.

    Adapted from Jinja2's builtin ``trim`` filter.
    """
    return soft_unicode(value).strip(what)

def flatten_filter(value):
    """Combine incoming sequences in one."""
    seq = []
    for s in value:
        seq.extend(s)
    return seq


# -- Jinja2 custom tests

def is_not_equalto(a, b):
    return a != b

def is_greaterthan(a, b):
    return a > b

def is_greaterthanorequal(a, b):
    return a >= b

def is_lessthan(a, b):
    return a < b

def is_lessthanorequal(a, b):
    return a <= b

def is_in(a, b):
    return a in b

def is_not_in(a, b):
    return a not in b

# Note: see which of the following should become Jinja2 filters

def captioned_button(req, symbol, text):
    """Return symbol and text or only symbol, according to user preferences."""
    return symbol if req.session.get('ui.use_symbols') \
        else u'%s %s' % (symbol, text)


def first_last(idx, seq):
    """Generate ``first`` or ``last`` or both, according to the
    position `idx` in sequence `seq`.

    In Jinja2 templates, rather use:

    .. sourcecode:: html+jinja

       <li ${{'class': {'first': loop.first, 'last': loop.last}}|htmlattr}>

    This is less error prone, as the sequence remains implicit and
    therefore can't be wrong.

    """
    return classes(first=idx == 0, last=idx == len(seq) - 1)


def group(iterable, num, predicate=None):
    """Combines the elements produced by the given iterable so that every `n`
    items are returned as a tuple.

    >>> items = [1, 2, 3, 4]
    >>> for item in group(items, 2):
    ...     print(item)
    (1, 2)
    (3, 4)

    The last tuple is padded with `None` values if its' length is smaller than
    `num`.

    >>> items = [1, 2, 3, 4, 5]
    >>> for item in group(items, 2):
    ...     print(item)
    (1, 2)
    (3, 4)
    (5, None)

    The optional `predicate` parameter can be used to flag elements that should
    not be packed together with other items. Only those elements where the
    predicate function returns True are grouped with other elements, otherwise
    they are returned as a tuple of length 1:

    >>> items = [1, 2, 3, 4]
    >>> for item in group(items, 2, lambda x: x != 3):
    ...     print(item)
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


@contextfilter
def groupattr_filter(_eval_ctx, iterable, num, attr, *args, **kwargs):
    """Similar to `group`, but as an attribute filter."""
    attr_getter = make_attrgetter(_eval_ctx.environment, attr)
    try:
        name = args[0]
        args = args[1:]
        test_func = lambda item: _eval_ctx.environment.call_test(name, item,
                                                                 args, kwargs)
    except LookupError:
        test_func = bool
    return group(iterable, num, lambda item: test_func(attr_getter(item)))


def istext(text):
    """`True` for text (`unicode` and `str`), but `False` for `Markup`."""
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

    >>> items = list(xrange(12))
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
    ...     for idx in xrange(12):
    ...         yield idx
    >>> paginate(generate())
    ([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 12, 2)
    >>> paginate(generate(), page=1)
    ([10, 11], 12, 2)

    The `max_per_page` parameter can be used to set the number of items that
    should be displayed per page:

    >>> items = xrange(12)
    >>> paginate(items, page=0, max_per_page=6)
    ([0, 1, 2, 3, 4, 5], 12, 2)
    >>> paginate(items, page=1, max_per_page=6)
    ([6, 7, 8, 9, 10, 11], 12, 2)

    :raises TracError: if `page` is out of the range of the paginated
                       results.
    """
    if not page:
        page = 0
    start = page * max_per_page
    stop = start + max_per_page

    count = None
    if hasattr(items, '__len__'):
        count = len(items)
        if count and start >= count:
            from trac.util.translation import _
            raise TracError(_("Page %(page)s is out of range.", page=page))

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
    """Pagination controller"""

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
        if not self.has_more_pages:
            return xrange(1, 2)

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

        return xrange(start_page, end_page + 1)

    def displayed_items(self):
        from trac.util.translation import _
        start, stop = self.span
        total = self.num_items
        if start + 1 == stop:
            return _("%(last)d of %(total)d", last=stop, total=total)
        else:
            return _("%(start)d - %(stop)d of %(total)d",
                    start=self.span[0] + 1, stop=self.span[1], total=total)


def separated(items, sep=',', last=None):
    """Yield `(item, sep)` tuples, one for each element in `items`.

    The separator after the last item is specified by the `last` parameter,
    which defaults to `None`. (Since 1.1.3)

    >>> list(separated([1, 2]))
    [(1, ','), (2, None)]

    >>> list(separated([1]))
    [(1, None)]

    >>> list(separated('abc', ':'))
    [('a', ':'), ('b', ':'), ('c', None)]

    >>> list(separated((1, 2, 3), sep=';', last='.'))
    [(1, ';'), (2, ';'), (3, '.')]
    """
    items = iter(items)
    nextval = next(items)
    for i in items:
        yield nextval, sep
        nextval = i
    yield nextval, last


_js_quote = {c: '\\u%04x' % ord(c) for c in '&<>'}
_js_quote_re = re.compile('[' + ''.join(_js_quote) + ']')

class TracJSONEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, Undefined):
            return ''
        elif isinstance(o, datetime):
            return to_utimestamp(o if o.tzinfo else o.replace(tzinfo=utc))
        elif isinstance(o, Fragment):
            return '"%s"' % javascript_quote(unicode(o))
        return JSONEncoder.default(self, o)

def to_json(value):
    """Encode `value` to JSON."""
    def replace(match):
        return _js_quote[match.group(0)]
    text = TracJSONEncoder(sort_keys=True, separators=(',', ':')).encode(value)
    return _js_quote_re.sub(replace, text)
