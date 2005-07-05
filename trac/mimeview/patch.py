# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
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
# Author: Christopher Lenz <cmlenz@gmx.de>
#         Ludvig Strigeus
#

from trac.core import *
from trac.mimeview.api import IHTMLPreviewRenderer
from trac.util import escape
from trac.web.chrome import add_stylesheet

__all__ = ['PatchRenderer']


class PatchRenderer(Component):
    """
    Structured display of patches in unified diff format, similar to the layout
    provided by the changeset view.
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
    <th title="<?cs var:file.oldrev ?>"><?cs var:file.oldrev ?></th>
    <th title="<?cs var:file.newrev ?>"><?cs var:item.newrev ?></th>
    <th>&nbsp;</th>
   </tr></thead><?cs
   each:change = file.diff ?><?cs
    call:diff_display(change, diff.style) ?><?cs
    if:name(change) < len(item.diff) - 1 ?>
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

        tabwidth = int(self.config.get('diff', 'tab_width'))
        d = self._diff_to_hdf(content.splitlines(), tabwidth)
        if not d:
            raise TracError, 'Invalid unified diff content'
        hdf = HDFWrapper(loadpaths=[self.env.get_templates_dir(),
                                    self.config.get('trac', 'templates_dir')])
        hdf['diff.files'] = d

        add_stylesheet(req, 'css/diff.css')
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
        for line in difflines:
            if line.startswith('--- '):
                # Base filename/version
                words = line.split(None, 2)
                filename, fromrev = words[1], 'old'
                groups, blocks = None, None
                continue
            if line.startswith('+++ '):
                # Changed filename/version
                words = line.split(None, 2)
                if len(words[1]) < len(filename):
                    # Always use the shortest filename for display
                    filename = words[1]
                groups = []
                output.append({'filename' : filename, 'oldrev' : fromrev,
                               'newrev' : 'new', 'diff' : groups})
                continue
            # Lines to ignore
            if line.startswith('Index: ') or line.startswith('======') or line == '':
                continue
            if groups == None:
                return None
            # @@ -333,10 +329,8 @@
            if line.startswith('@@ '):
                r = re.match(r'@@ -(\d+),\d+ \+(\d+),\d+ @@', line)
                if not r:
                    return None
                blocks = []
                groups.append(blocks)
                fromline,toline = map(int, r.groups())
                last_type = None
                continue
            if blocks == None:
                return None

            # First character is the command
            command,line = line[0],line[1:]

            # Make a new block?
            if (command == ' ') != last_type:
                last_type = command == ' '
                blocks.append({'type': last_type and 'unmod' or 'mod',
                               'base.offset': fromline, 'base.lines': [],
                               'changed.offset': toline,'changed.lines': []})
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
                        f[i] = space_re.sub(htmlify, line)
                    for i in xrange(len(t)):
                        line = t[i].expandtabs(tabwidth)
                        line = escape(line).replace('\0', '<ins>') \
                                           .replace('\1', '</ins>')
                        t[i] = space_re.sub(htmlify, line)
        return output
