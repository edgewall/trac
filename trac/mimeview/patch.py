# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Christian Boos <cboos@edgewall.org>
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
#         Ludvig Strigeus

import os.path
import re

from trac.core import *
from trac.mimeview.api import content_to_unicode, IHTMLPreviewRenderer, \
                              Mimeview
from trac.util.html import escape, Markup
from trac.util.text import expandtabs
from trac.util.translation import _
from trac.web.chrome import Chrome, add_script, add_stylesheet

__all__ = ['PatchRenderer']


class PatchRenderer(Component):
    """HTML renderer for patches in unified diff format.

    This uses the same layout as in the wiki diff view or the changeset view.
    """

    implements(IHTMLPreviewRenderer)

    # IHTMLPreviewRenderer methods

    def get_quality_ratio(self, mimetype):
        if mimetype in ('text/x-diff', 'text/x-patch'):
            return 8
        return 0

    def render(self, context, mimetype, content, filename=None, rev=None):
        req = context.req
        content = content_to_unicode(self.env, content, mimetype)
        changes = self._diff_to_hdf(content.splitlines(),
                                    Mimeview(self.env).tab_width)
        if not changes or not any(c['diffs'] for c in changes):
            self.log.debug("Invalid unified diff content: %.40r... (%d "
                           "characters)", content, len(content))
            return
        data = {'diff': {'style': 'inline'}, 'no_id': True,
                'changes': changes, 'longcol': 'File', 'shortcol': ''}

        add_script(req, 'common/js/diff.js')
        add_stylesheet(req, 'common/css/diff.css')
        return Chrome(self.env).render_template(req, 'diff_div.html',
                                                data, fragment=True)

    # Internal methods

    # FIXME: This function should probably share more code with the
    #        trac.versioncontrol.diff module
    def _diff_to_hdf(self, difflines, tabwidth):
        """
        Translate a diff file into something suitable for inclusion in HDF.
        The result is [(filename, revname_old, revname_new, changes)],
        where changes has the same format as the result of
        `trac.versioncontrol.diff.hdf_diff`.

        If the diff cannot be parsed, this method returns None.
        """
        def _markup_intraline_change(fromlines, tolines):
            from trac.versioncontrol.diff import get_change_extent
            for i in xrange(len(fromlines)):
                fr, to = fromlines[i], tolines[i]
                (start, end) = get_change_extent(fr, to)
                if start != 0 or end != 0:
                    last = end+len(fr)
                    fromlines[i] = fr[:start] + '\0' + fr[start:last] + \
                                   '\1' + fr[last:]
                    last = end+len(to)
                    tolines[i] = to[:start] + '\0' + to[start:last] + \
                                 '\1' + to[last:]

        space_re = re.compile(' ( +)|^ ')
        def htmlify(match):
            div, mod = divmod(len(match.group(0)), 2)
            return div * '&nbsp; ' + mod * '&nbsp;'

        comments = []
        changes = []
        lines = iter(difflines)
        try:
            line = lines.next()
            while True:
                oldpath = oldrev = newpath = newrev = ''
                oldinfo = newinfo = []
                binary = False

                # consume preample, storing free lines in comments
                # (also detect the special case of git binary patches)
                if not line.startswith('--- '):
                    if not line.startswith('Index: ') and line != '=' * 67:
                        comments.append(line)
                    if line == "GIT binary patch":
                        binary = True
                        diffcmd_line = comments[0] # diff --git a/... b/,,,
                        oldpath, newpath = diffcmd_line.split()[-2:]
                        if any(c.startswith('new file') for c in comments):
                            oldpath = '/dev/null'
                        if any(c.startswith('deleted file') for c in comments):
                            newpath = '/dev/null'
                        oldinfo = ['', oldpath]
                        newinfo = ['', newpath]
                        index = [c for c in comments if c.startswith('index ')]
                        if index: # index 8f****78..1e****5c
                            oldrev, newrev = index[0].split()[-1].split('..')
                            oldinfo.append(oldrev)
                            newinfo.append(newrev)
                        line = lines.next()
                        while line:
                            comments.append(line)
                            line = lines.next()
                    else:
                        line = lines.next()
                        continue

                if not oldinfo and not newinfo:
                    # Base filename/version from '--- <file> [rev]'
                    oldinfo = line.split(None, 2)
                    if len(oldinfo) > 1:
                        oldpath = oldinfo[1]
                        if len(oldinfo) > 2:
                            oldrev = oldinfo[2]

                    # Changed filename/version from '+++ <file> [rev]'
                    line = lines.next()
                    if not line.startswith('+++ '):
                        self.log.debug('expected +++ after ---, got %s', line)
                        return None

                    newinfo = line.split(None, 2)
                    if len(newinfo) > 1:
                        newpath = newinfo[1]
                        if len(newinfo) > 2:
                            newrev = newinfo[2]

                shortrev = ('old', 'new')
                if oldpath or newpath:
                    sep = re.compile(r'([/.~\\])')
                    commonprefix = ''.join(os.path.commonprefix(
                        [sep.split(newpath), sep.split(oldpath)]))
                    commonsuffix = ''.join(os.path.commonprefix(
                        [sep.split(newpath)[::-1],
                         sep.split(oldpath)[::-1]])[::-1])
                    if len(commonprefix) > len(commonsuffix):
                        common = commonprefix
                    elif commonsuffix:
                        common = commonsuffix.lstrip('/')
                        a = oldpath[:-len(commonsuffix)]
                        b = newpath[:-len(commonsuffix)]
                        if len(a) < 4 and len(b) < 4:
                            shortrev = (a, b)
                    elif oldpath == '/dev/null':
                        common = _("new file %(new)s",
                                   new=newpath.lstrip('b/'))
                        shortrev = ('-', '+')
                    elif newpath == '/dev/null':
                        common = _("deleted file %(deleted)s",
                                   deleted=oldpath.lstrip('a/'))
                        shortrev = ('+', '-')
                    else:
                        common = '(a) %s vs. (b) %s' % (oldpath, newpath)
                        shortrev = ('a', 'b')
                else:
                    common = ''

                groups = []
                groups_title = []
                changes.append({'change': 'edit', 'props': [],
                                'comments': '\n'.join(comments),
                                'binary': binary,
                                'diffs': groups,
                                'diffs_title': groups_title,
                                'old': {'path': common,
                                        'rev': ' '.join(oldinfo[1:]),
                                        'shortrev': shortrev[0]},
                                'new': {'path': common,
                                        'rev': ' '.join(newinfo[1:]),
                                        'shortrev': shortrev[1]}})
                comments = []
                line = lines.next()
                while line:
                    # "@@ -333,10 +329,8 @@" or "@@ -1 +1 @@ [... title ...]"
                    r = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@'
                                  '(.*)', line)
                    if not r:
                        break
                    blocks = []
                    groups.append(blocks)
                    fromline, fromend, toline, toend = \
                            [int(x or 1) for x in r.groups()[:4]]
                    groups_title.append(r.group(5))
                    last_type = extra = None

                    fromend += fromline
                    toend += toline
                    line = lines.next()
                    while fromline < fromend or toline < toend or extra:

                        # First character is the command
                        command = ' '
                        if line:
                            command, line = line[0], line[1:]
                        # Make a new block?
                        if (command == ' ') != last_type:
                            last_type = command == ' '
                            kind = 'unmod' if last_type else 'mod'
                            block = {'type': kind,
                                     'base': {'offset': fromline - 1,
                                              'lines': []},
                                     'changed': {'offset': toline - 1,
                                                 'lines': []}}
                            blocks.append(block)
                        else:
                            block = blocks[-1]
                        if command == ' ':
                            sides = ['base', 'changed']
                        elif command == '+':
                            last_side = 'changed'
                            sides = [last_side]
                        elif command == '-':
                            last_side = 'base'
                            sides = [last_side]
                        elif command == '\\' and last_side:
                            meta = block[last_side].setdefault('meta', {})
                            meta[len(block[last_side]['lines'])] = True
                            sides = [last_side]
                        elif command == '@': # ill-formed patch
                            groups_title[-1] = "%s (%s)" % (
                                groups_title[-1],
                                _("this hunk was shorter than expected"))
                            line = '@'+line
                            break
                        else:
                            self.log.debug('expected +, - or \\, got %s',
                                           command)
                            return None
                        for side in sides:
                            if side == 'base':
                                fromline += 1
                            else:
                                toline += 1
                            block[side]['lines'].append(line)
                        line = lines.next()
                        extra = line and line[0] == '\\'
        except StopIteration:
            pass

        # Go through all groups/blocks and mark up intraline changes, and
        # convert to html
        for o in changes:
            for group in o['diffs']:
                for b in group:
                    base, changed = b['base'], b['changed']
                    f, t = base['lines'], changed['lines']
                    if b['type'] == 'mod':
                        if len(f) == 0:
                            b['type'] = 'add'
                        elif len(t) == 0:
                            b['type'] = 'rem'
                        elif len(f) == len(t):
                            _markup_intraline_change(f, t)
                    for i in xrange(len(f)):
                        line = expandtabs(f[i], tabwidth, '\0\1')
                        line = escape(line, quotes=False)
                        line = '<del>'.join([space_re.sub(htmlify, seg)
                                             for seg in line.split('\0')])
                        line = line.replace('\1', '</del>')
                        f[i] = Markup(line)
                        if 'meta' in base and i in base['meta']:
                            f[i] = Markup('<em>%s</em>') % f[i]
                    for i in xrange(len(t)):
                        line = expandtabs(t[i], tabwidth, '\0\1')
                        line = escape(line, quotes=False)
                        line = '<ins>'.join([space_re.sub(htmlify, seg)
                                             for seg in line.split('\0')])
                        line = line.replace('\1', '</ins>')
                        t[i] = Markup(line)
                        if 'meta' in changed and i in changed['meta']:
                            t[i] = Markup('<em>%s</em>') % t[i]
        return changes
