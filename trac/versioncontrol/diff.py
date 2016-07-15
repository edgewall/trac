# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2009 Edgewall Software
# Copyright (C) 2004-2006 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

import difflib
import re

from trac.util.html import Markup, escape
from trac.util.text import expandtabs

__all__ = ['diff_blocks', 'get_change_extent', 'get_diff_options',
           'unified_diff']

_whitespace_split = re.compile(r'\s+', re.UNICODE).split


def _norm_space_changes(text):
    return ' '.join(_whitespace_split(text))


def get_change_extent(str1, str2):
    """Determines the extent of differences between two strings.

    Returns a pair containing the offset at which the changes start,
    and the negative offset at which the changes end.

    If the two strings have neither a common prefix nor a common
    suffix, ``(0, 0)`` is returned.
    """
    start = 0
    limit = min(len(str1), len(str2))
    while start < limit and str1[start] == str2[start]:
        start += 1
    end = -1
    limit = limit - start
    while -end <= limit and str1[end] == str2[end]:
        end -= 1
    return (start, end + 1)


def get_filtered_hunks(fromlines, tolines, context=None,
                       ignore_blank_lines=False, ignore_case=False,
                       ignore_space_changes=False):
    """Retrieve differences in the form of `difflib.SequenceMatcher`
    opcodes, grouped according to the ``context`` and ``ignore_*``
    parameters.

    :param fromlines: list of lines corresponding to the old content
    :param tolines: list of lines corresponding to the new content
    :param ignore_blank_lines: differences about empty lines only are ignored
    :param ignore_case: upper case / lower case only differences are ignored
    :param ignore_space_changes: differences in amount of spaces are ignored
    :param context: the number of "equal" lines kept for representing
                    the context of the change
    :return: generator of grouped `difflib.SequenceMatcher` opcodes

    If none of the ``ignore_*`` parameters is `True`, there's nothing
    to filter out the results will come straight from the
    SequenceMatcher.
    """
    if ignore_space_changes:
        fromlines = map(_norm_space_changes, fromlines)
        tolines = map(_norm_space_changes, tolines)
    if ignore_case:
        fromlines = [l.lower() for l in fromlines]
        tolines = [l.lower() for l in tolines]
    hunks = get_hunks(fromlines, tolines, context)
    if ignore_blank_lines:
        hunks = filter_ignorable_lines(hunks, fromlines, tolines, context,
                                       ignore_blank_lines, False, False)
    return hunks


def get_hunks(fromlines, tolines, context=None):
    """Generator yielding grouped opcodes describing differences .

    See `get_filtered_hunks` for the parameter descriptions.
    """
    matcher = difflib.SequenceMatcher(None, fromlines, tolines)
    if context is None:
        return (hunk for hunk in [matcher.get_opcodes()])
    else:
        return matcher.get_grouped_opcodes(context)


def filter_ignorable_lines(hunks, fromlines, tolines, context,
                           ignore_blank_lines, ignore_case,
                           ignore_space_changes):
    """Detect line changes that should be ignored and emits them as
    tagged as "equal", possibly joined with the preceding and/or
    following "equal" block.

    See `get_filtered_hunks` for the parameter descriptions.
    """
    def is_ignorable(tag, fromlines, tolines):
        if ignore_blank_lines:
            if tag == 'delete':
                return not any(fromlines)
            if tag == 'insert':
                return not any(tolines)
        if (ignore_case or ignore_space_changes) and tag == 'replace':
            if len(fromlines) != len(tolines):
                return False
            def f(str):
                if ignore_case:
                    str = str.lower()
                if ignore_space_changes:
                    str = _norm_space_changes(str)
                return str
            for i in range(len(fromlines)):
                if f(fromlines[i]) != f(tolines[i]):
                    return False
            return True

    hunks = list(hunks)
    opcodes = []
    ignored_lines = False
    prev = None
    for hunk in hunks:
        for tag, i1, i2, j1, j2 in hunk:
            if tag == 'equal':
                if prev:
                    prev = (tag, prev[1], i2, prev[3], j2)
                else:
                    prev = (tag, i1, i2, j1, j2)
            else:
                if is_ignorable(tag, fromlines[i1:i2], tolines[j1:j2]):
                    ignored_lines = True
                    if prev:
                        prev = 'equal', prev[1], i2, prev[3], j2
                    else:
                        prev = 'equal', i1, i2, j1, j2
                    continue
                if prev:
                    opcodes.append(prev)
                opcodes.append((tag, i1, i2, j1, j2))
                prev = None
    if prev:
        opcodes.append(prev)

    if ignored_lines:
        if context is None:
            yield opcodes
        else:
            # we leave at most n lines with the tag 'equal' before and after
            # every change
            n = context
            nn = n + n

            group = []
            def all_equal():
                all(op[0] == 'equal' for op in group)
            for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes):
                if idx == 0 and tag == 'equal': # Fixup leading unchanged block
                    i1, j1 = max(i1, i2 - n), max(j1, j2 - n)
                elif tag == 'equal' and i2 - i1 > nn:
                    group.append((tag, i1, min(i2, i1 + n), j1,
                                  min(j2, j1 + n)))
                    if not all_equal():
                        yield group
                    group = []
                    i1, j1 = max(i1, i2 - n), max(j1, j2 - n)
                group.append((tag, i1, i2, j1, j2))

            if group and not (len(group) == 1 and group[0][0] == 'equal'):
                if group[-1][0] == 'equal': # Fixup trailing unchanged block
                    tag, i1, i2, j1, j2 = group[-1]
                    group[-1] = tag, i1, min(i2, i1 + n), j1, min(j2, j1 + n)
                if not all_equal():
                    yield group
    else:
        for hunk in hunks:
            yield hunk


def diff_blocks(fromlines, tolines, context=None, tabwidth=8,
                ignore_blank_lines=0, ignore_case=0, ignore_space_changes=0):
    """Return an array that is adequate for adding to the data dictionary

    See `get_filtered_hunks` for the parameter descriptions.

    See also the diff_div.html template.
    """

    type_map = {'replace': 'mod', 'delete': 'rem', 'insert': 'add',
                'equal': 'unmod'}

    space_re = re.compile(' ( +)|^ ')
    def htmlify(match):
        div, mod = divmod(len(match.group(0)), 2)
        return div * '&nbsp; ' + mod * '&nbsp;'

    def markup_intraline_changes(opcodes):
        for tag, i1, i2, j1, j2 in opcodes:
            if tag == 'replace' and i2 - i1 == j2 - j1:
                for i in range(i2 - i1):
                    fromline, toline = fromlines[i1 + i], tolines[j1 + i]
                    (start, end) = get_change_extent(fromline, toline)
                    if start != 0 or end != 0:
                        last = end + len(fromline)
                        fromlines[i1 + i] = (
                            fromline[:start] + '\0' + fromline[start:last] +
                            '\1' + fromline[last:])
                        last = end+len(toline)
                        tolines[j1 + i] = (
                            toline[:start] + '\0' + toline[start:last] +
                            '\1' + toline[last:])
            yield tag, i1, i2, j1, j2

    changes = []
    for group in get_filtered_hunks(fromlines, tolines, context,
                                    ignore_blank_lines, ignore_case,
                                    ignore_space_changes):
        blocks = []
        last_tag = None
        for tag, i1, i2, j1, j2 in markup_intraline_changes(group):
            if tag != last_tag:
                blocks.append({'type': type_map[tag],
                               'base': {'offset': i1, 'lines': []},
                               'changed': {'offset': j1, 'lines': []}})
            if tag == 'equal':
                for line in fromlines[i1:i2]:
                    line = line.expandtabs(tabwidth)
                    line = space_re.sub(htmlify, escape(line, quotes=False))
                    blocks[-1]['base']['lines'].append(Markup(unicode(line)))
                for line in tolines[j1:j2]:
                    line = line.expandtabs(tabwidth)
                    line = space_re.sub(htmlify, escape(line, quotes=False))
                    blocks[-1]['changed']['lines'].append(Markup(unicode(line)))
            else:
                if tag in ('replace', 'delete'):
                    for line in fromlines[i1:i2]:
                        line = expandtabs(line, tabwidth, '\0\1')
                        line = escape(line, quotes=False)
                        line = '<del>'.join([space_re.sub(htmlify, seg)
                                             for seg in line.split('\0')])
                        line = line.replace('\1', '</del>')
                        blocks[-1]['base']['lines'].append(
                            Markup(unicode(line)))
                if tag in ('replace', 'insert'):
                    for line in tolines[j1:j2]:
                        line = expandtabs(line, tabwidth, '\0\1')
                        line = escape(line, quotes=False)
                        line = '<ins>'.join([space_re.sub(htmlify, seg)
                                             for seg in line.split('\0')])
                        line = line.replace('\1', '</ins>')
                        blocks[-1]['changed']['lines'].append(
                            Markup(unicode(line)))
        changes.append(blocks)
    return changes


def unified_diff(fromlines, tolines, context=None, ignore_blank_lines=0,
                 ignore_case=0, ignore_space_changes=0):
    """Generator producing lines corresponding to a textual diff.

    See `get_filtered_hunks` for the parameter descriptions.
    """
    for group in get_filtered_hunks(fromlines, tolines, context,
                                    ignore_blank_lines, ignore_case,
                                    ignore_space_changes):
        i1, i2, j1, j2 = group[0][1], group[-1][2], group[0][3], group[-1][4]
        if i1 == 0 and i2 == 0:
            i1, i2 = -1, -1 # support for 'A'dd changes
        yield '@@ -%d,%d +%d,%d @@' % (i1 + 1, i2 - i1, j1 + 1, j2 - j1)
        for tag, i1, i2, j1, j2 in group:
            if tag == 'equal':
                for line in fromlines[i1:i2]:
                    yield ' ' + line
            else:
                if tag in ('replace', 'delete'):
                    for line in fromlines[i1:i2]:
                        yield '-' + line
                if tag in ('replace', 'insert'):
                    for line in tolines[j1:j2]:
                        yield '+' + line


def get_diff_options(req):
    """Retrieve user preferences for diffs.

    :return: ``(style, options, data)`` triple.

      ``style``
        can be ``'inline'`` or ``'sidebyside'``,
      ``options``
        a sequence of "diff" flags,
      ``data``
        the style and options information represented as
        key/value pairs in dictionaries, for example::

          {'style': u'sidebyside',
           'options': {'contextall': 1, 'contextlines': 2,
                       'ignorecase': 0,  'ignoreblanklines': 0,
                       'ignorewhitespace': 1}}

    """
    options_data = {}
    data = {'options': options_data}

    def get_bool_option(name, default=0):
        pref = req.session.as_int('diff_' + name, default)
        arg = int(name in req.args)
        if 'update' in req.args and arg != pref:
            req.session.set('diff_' + name, arg, default)
        else:
            arg = pref
        return arg

    pref = req.session.get('diff_style', 'inline')
    style = req.args.get('style', pref)
    if 'update' in req.args and style != pref:
        req.session.set('diff_style', style, 'inline')
    data['style'] = style

    pref = req.session.as_int('diff_contextlines', 2)
    context = req.args.as_int('contextlines', pref)
    if 'update' in req.args and context != pref:
        req.session.set('diff_contextlines', context, 2)
    options_data['contextlines'] = context

    arg = req.args.as_int('contextall', 0)
    options_data['contextall'] = arg
    options = ['-U%d' % (-1 if arg else context)]

    arg = get_bool_option('ignoreblanklines')
    if arg:
        options.append('-B')
    options_data['ignoreblanklines'] = arg

    arg = get_bool_option('ignorecase')
    if arg:
        options.append('-i')
    options_data['ignorecase'] = arg

    arg = get_bool_option('ignorewhitespace')
    if arg:
        options.append('-b')
    options_data['ignorewhitespace'] = arg

    return (style, options, data)
