# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2006 Edgewall Software
# Copyright (C) 2004-2006 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from trac.util.markup import escape, Markup

from difflib import SequenceMatcher
import re

__all__ = ['get_diff_options', 'hdf_diff', 'unified_diff']


def _get_change_extent(str1, str2):
    """
    Determines the extent of differences between two strings. Returns a tuple
    containing the offset at which the changes start, and the negative offset
    at which the changes end. If the two strings have neither a common prefix
    nor a common suffix, (0, 0) is returned.
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

def _get_opcodes(fromlines, tolines, ignore_blank_lines=False,
                 ignore_case=False, ignore_space_changes=False):
    """
    Generator built on top of SequenceMatcher.get_opcodes().
    
    This function detects line changes that should be ignored and emits them
    as tagged as 'equal', possibly joined with the preceding and/or following
    'equal' block.
    """

    def is_ignorable(tag, fromlines, tolines):
        if tag == 'delete' and ignore_blank_lines:
            if ''.join(fromlines) == '':
                return True
        elif tag == 'insert' and ignore_blank_lines:
            if ''.join(tolines) == '':
                return True
        elif tag == 'replace' and (ignore_case or ignore_space_changes):
            if len(fromlines) != len(tolines):
                return False
            def f(str):
                if ignore_case:
                    str = str.lower()
                if ignore_space_changes:
                    str = ' '.join(str.split())
                return str
            for i in range(len(fromlines)):
                if f(fromlines[i]) != f(tolines[i]):
                    return False
            return True

    matcher = SequenceMatcher(None, fromlines, tolines)
    previous = None
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            if previous:
                previous = (tag, previous[1], i2, previous[3], j2)
            else:
                previous = (tag, i1, i2, j1, j2)
        else:
            if is_ignorable(tag, fromlines[i1:i2], tolines[j1:j2]):
                if previous:
                    previous = 'equal', previous[1], i2, previous[3], j2
                else:
                    previous = 'equal', i1, i2, j1, j2
                continue
            if previous:
                yield previous
            yield tag, i1, i2, j1, j2
            previous = None

    if previous:
        yield previous

def _group_opcodes(opcodes, n=3):
    """
    Python 2.2 doesn't have SequenceMatcher.get_grouped_opcodes(), so let's
    provide equivalent here. The opcodes parameter can be any iterable or
    sequence.

    This function can also be used to generate full-context diffs by passing 
    None for the parameter n.
    """
    # Full context produces all the opcodes
    if n is None:
        yield opcodes
        return

    # Otherwise we leave at most n lines with the tag 'equal' before and after
    # every change
    nn = n + n
    group = []
    for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if idx == 0 and tag == 'equal': # Fixup leading unchanged block
            i1, j1 = max(i1, i2 - n), max(j1, j2 - n)
        elif tag == 'equal' and i2 - i1 > nn:
            group.append((tag, i1, min(i2, i1 + n), j1, min(j2, j1 + n)))
            yield group
            group = []
            i1, j1 = max(i1, i2 - n), max(j1, j2 - n)
        group.append((tag, i1, i2, j1 ,j2))

    if group and not (len(group) == 1 and group[0][0] == 'equal'):
        if group[-1][0] == 'equal': # Fixup trailing unchanged block
            tag, i1, i2, j1, j2 = group[-1]
            group[-1] = tag, i1, min(i2, i1 + n), j1, min(j2, j1 + n)
        yield group

def hdf_diff(fromlines, tolines, context=None, tabwidth=8,
             ignore_blank_lines=0, ignore_case=0, ignore_space_changes=0):
    """
    Return an array that is adequate for adding the the HDF data set for HTML
    rendering of the differences.
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
                    (start, end) = _get_change_extent(fromline, toline)

                    if start == 0 and end < 0:
                        # Change at start of line
                        fromlines[i1 + i] = '\0' + fromline[:end] + '\1' + \
                                            fromline[end:]
                        tolines[j1 + i] = '\0' + toline[:end] + '\1' + \
                                          toline[end:]
                    elif start > 0 and end == 0:
                        # Change at end of line
                        fromlines[i1 + i] = fromline[:start] + '\0' + \
                                            fromline[start:] + '\1'
                        tolines[j1 + i] = toline[:start] + '\0' + \
                                          toline[start:] + '\1'
                    elif start > 0 and end < 0:
                        # Change somewhere in the middle
                        fromlines[i1 + i] = fromline[:start] + '\0' + \
                                            fromline[start:end] + '\1' + \
                                            fromline[end:]
                        tolines[j1 + i] = toline[:start] + '\0' + \
                                          toline[start:end] + '\1' + \
                                          toline[end:]
            yield tag, i1, i2, j1, j2

    changes = []
    opcodes = _get_opcodes(fromlines, tolines, ignore_blank_lines, ignore_case,
                           ignore_space_changes)
    for group in _group_opcodes(opcodes, context):
        blocks = []
        last_tag = None
        for tag, i1, i2, j1, j2 in markup_intraline_changes(group):
            if tag != last_tag:
                blocks.append({'type': type_map[tag], 'base.offset': i1,
                               'base.lines': [], 'changed.offset': j1,
                               'changed.lines': []})
            if tag == 'equal':
                for line in fromlines[i1:i2]:
                    line = line.expandtabs(tabwidth)
                    line = space_re.sub(htmlify, escape(line, quotes=False))
                    blocks[-1]['base.lines'].append(Markup(line))
                for line in tolines[j1:j2]:
                    line = line.expandtabs(tabwidth)
                    line = space_re.sub(htmlify, escape(line, quotes=False))
                    blocks[-1]['changed.lines'].append(Markup(line))
            else:
                if tag in ('replace', 'delete'):
                    for line in fromlines[i1:i2]:
                        line = line.expandtabs(tabwidth)
                        line = escape(line, quotes=False).replace('\0', '<del>') \
                                                         .replace('\1', '</del>')
                        blocks[-1]['base.lines'].append(Markup(space_re.sub(htmlify,
                                                                            line)))
                if tag in ('replace', 'insert'):
                    for line in tolines[j1:j2]:
                        line = line.expandtabs(tabwidth)
                        line = escape(line, quotes=False).replace('\0', '<ins>') \
                                                         .replace('\1', '</ins>')
                        blocks[-1]['changed.lines'].append(Markup(space_re.sub(htmlify,
                                                                               line)))
        changes.append(blocks)
    return changes

def unified_diff(fromlines, tolines, context=None, ignore_blank_lines=0,
                 ignore_case=0, ignore_space_changes=0):
    opcodes = _get_opcodes(fromlines, tolines, ignore_blank_lines, ignore_case,
                           ignore_space_changes)
    for group in _group_opcodes(opcodes, context):
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

    def get_bool_option(name, default=0):
        pref = int(req.session.get('diff_' + name, default))
        arg = int(req.args.has_key(name))
        if req.args.has_key('update') and arg != pref:
            req.session['diff_' + name] = arg
        else:
            arg = pref
        return arg

    pref = req.session.get('diff_style', 'inline')
    style = req.args.get('style', pref)
    if req.args.has_key('update') and style != pref:
        req.session['diff_style'] = style
    req.hdf['diff.style'] = style

    pref = int(req.session.get('diff_contextlines', 2))
    try:
        arg = int(req.args.get('contextlines', pref))
    except ValueError:
        arg = -1
    if req.args.has_key('update') and arg != pref:
        req.session['diff_contextlines'] = arg
    options = ['-U%d' % arg]
    if arg >= 0:
        req.hdf['diff.options.contextlines'] = arg
    else:
        req.hdf['diff.options.contextlines'] = 'all'

    arg = get_bool_option('ignoreblanklines')
    if arg:
        options.append('-B')
    req.hdf['diff.options.ignoreblanklines'] = arg

    arg = get_bool_option('ignorecase')
    if arg:
        options.append('-i')
    req.hdf['diff.options.ignorecase'] = arg

    arg = get_bool_option('ignorewhitespace')
    if arg:
        options.append('-b')
    req.hdf['diff.options.ignorewhitespace'] = arg

    return (style, options)
