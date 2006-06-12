# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Ludvig Strigeus

from trac.core import *
from trac.mimeview.api import content_to_unicode, IHTMLPreviewRenderer, Mimeview
from trac.util.markup import escape, Markup
from trac.web.chrome import add_stylesheet

__all__ = ['PatchRenderer']


class PatchRenderer(Component):
    """Structured display of patches in unified diff format, similar to the
    layout provided by the changeset view.
    """

    implements(IHTMLPreviewRenderer)

    diff_cs = """
<?cs include:'macros.cs' ?>
<div class="diff"><ul class="entries"><?cs
 each:file = diff.files ?><li class="entry">
  <h2><?cs var:file.filename ?></h2>
  <table class="inline" summary="Differences" cellspacing="0">
   <colgroup><col class="lineno" /><col class="lineno" /><col class="content" /></colgroup>
   <thead><tr>
    <th><?cs var:file.oldrev ?></th>
    <th><?cs var:file.newrev ?></th>
    <th>&nbsp;</th>
   </tr></thead><?cs
   each:change = file.diff ?><?cs
    call:diff_display(change, diff.style) ?><?cs
    if:name(change) < len(file.diff) - 1 ?>
     <tbody class="skipped">
      <tr><th>&hellip;</th><th>&hellip;</th><td>&nbsp;</td></tr>
     </tbody><?cs
    /if ?><?cs
   /each ?>
  </table>
 </li><?cs /each ?>
</ul></div>
""" # diff_cs

    # IHTMLPreviewRenderer methods

    def get_quality_ratio(self, mimetype):
        if mimetype == 'text/x-diff':
            return 8
        return 0

    def render(self, req, mimetype, content, filename=None, rev=None):
        from trac.web.clearsilver import HDFWrapper

        content = content_to_unicode(self.env, content, mimetype)
        d = self._diff_to_hdf(content.splitlines(),
                              Mimeview(self.env).tab_width)
        if not d:
            raise TracError, 'Invalid unified diff content'
        hdf = HDFWrapper(loadpaths=[self.env.get_templates_dir(),
                                    self.config.get('trac', 'templates_dir')])
        hdf['diff.files'] = d

        add_stylesheet(req, 'common/css/diff.css')
        return hdf.render(hdf.parse(self.diff_cs))

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
            from trac.versioncontrol.diff import _get_change_extent
            for i in xrange(len(fromlines)):
                fr, to = fromlines[i], tolines[i]
                (start, end) = _get_change_extent(fr, to)
                if start != 0 and end != 0:
                    fromlines[i] = fr[:start] + '\0' + fr[start:end+len(fr)] + \
                                   '\1' + fr[end:]
                    tolines[i] = to[:start] + '\0' + to[start:end+len(to)] + \
                                 '\1' + to[end:]

        import re
        space_re = re.compile(' ( +)|^ ')
        def htmlify(match):
            div, mod = divmod(len(match.group(0)), 2)
            return div * '&nbsp; ' + mod * '&nbsp;'

        output = []
        filename, groups = None, None
        lines = iter(difflines)
        try:
            line = lines.next()
            while True:
                if not line.startswith('--- '):
                    line = lines.next()
                    continue

                # Base filename/version
                words = line.split(None, 2)
                filename, fromrev = words[1], 'old'
                groups, blocks = None, None

                # Changed filename/version
                line = lines.next()
                if not line.startswith('+++ '):
                    return None

                words = line.split(None, 2)
                if len(words[1]) < len(filename):
                    # Always use the shortest filename for display
                    filename = words[1]
                groups = []
                output.append({'filename' : filename, 'oldrev' : fromrev,
                               'newrev' : 'new', 'diff' : groups})

                for line in lines:
                    # @@ -333,10 +329,8 @@
                    r = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', line)
                    if not r:
                        break
                    blocks = []
                    groups.append(blocks)
                    fromline,fromend,toline,toend = map(int, r.groups())
                    last_type = None

                    fromend += fromline
                    toend += toline

                    while fromline < fromend or toline < toend:
                        line = lines.next()

                        # First character is the command
                        command, line = line[0], line[1:]
                        # Make a new block?
                        if (command == ' ') != last_type:
                            last_type = command == ' '
                            blocks.append({'type': last_type and 'unmod' or 'mod',
                                           'base.offset': fromline - 1,
                                           'base.lines': [],
                                           'changed.offset': toline - 1,
                                           'changed.lines': []})
                        if command == ' ':
                            blocks[-1]['changed.lines'].append(line)
                            blocks[-1]['base.lines'].append(line)
                            fromline += 1
                            toline += 1
                        elif command == '+':
                            blocks[-1]['changed.lines'].append(line)
                            toline += 1
                        elif command == '-':
                            blocks[-1]['base.lines'].append(line)
                            fromline += 1
                        else:
                            return None
                line = lines.next()
        except StopIteration:
            pass

        # Go through all groups/blocks and mark up intraline changes, and
        # convert to html
        for o in output:
            for group in o['diff']:
                for b in group:
                    f, t = b['base.lines'], b['changed.lines']
                    if b['type'] == 'mod':
                        if len(f) == 0:
                            b['type'] = 'add'
                        elif len(t) == 0:
                            b['type'] = 'rem'
                        elif len(f) == len(t):
                            _markup_intraline_change(f, t)
                    for i in xrange(len(f)):
                        line = f[i].expandtabs(tabwidth)
                        line = escape(line).replace('\0', '<del>') \
                                           .replace('\1', '</del>')
                        f[i] = Markup(space_re.sub(htmlify, line))
                    for i in xrange(len(t)):
                        line = t[i].expandtabs(tabwidth)
                        line = escape(line).replace('\0', '<ins>') \
                                           .replace('\1', '</ins>')
                        t[i] = Markup(space_re.sub(htmlify, line))
        return output
