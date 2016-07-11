#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
# Copyright (C) 2013 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

"""

L10N tool which prepares an index of "interesting" changes found in a
.diff.

Skipped changes are:
 - the changes for which the msgid has changed
 - removal only of msgstr content


Example workflow 1), review changes to the 'fr' translation before
committing:

  make diff-fr | less


Example workflow 2), force a pull of all changes from Transifex::

  make update updateopts=-N
  tx pull -f
  make update updateopts=-N
  svn diff > tx.diff
  python l10n_diff_index.py tx.diff
  svn revert -R .

And then use either::

  emacs tx.diff.index --eval '(grep-mode)'

or::

  vim -c :cbuffer -c :copen tx.diff.index

This makes it easier to go through the potentially interesting changes
only, and apply the corresponding chunks if needed.

"""

from bisect import bisect_left
import re

interesting_changes_re = re.compile(r'''
                                               \n
       \s (?: msgid(?:_plural)?\s)? ".*"       \n  # ' ' msgid or "...",
   (?:
       [-\s]  ".*"                             \n  # ' ' or - "...",
   |
       -      msgstr(?:\[\d+\])? \s ".*"       \n  # or the -msgstr
   )*

 (?:
     ( \+     msgstr(?:\[\d+\])? \s "[^"].*" ) \n  # \1 is a non-empty +msgstr
 |
       [+\s]  msgstr(?:\[\d+\])? \s ".*"       \n  # or after the msgstr,
   (?: [-\s]  ".*"                             \n  # optional ' ' or -"...",
   )*
     ( \+     "[^"].*" )                           # \2 is a non-empty +"..."
 )
''', re.MULTILINE | re.VERBOSE)

def index_diffs(path, diffs):
    linenums = []
    re.sub(r'\n', lambda m: linenums.append(m.start()), diffs)
    index = []
    for m in interesting_changes_re.finditer(diffs):
        line = m.group(m.lastindex)
        if line.startswith(('+"Project-Id-Version:', '+"PO-Revision-Date:')):
            continue
        pos = m.start(m.lastindex)
        index.append((bisect_left(linenums, pos) + 1, line))
    return index

def write_index_for(path):
    with open(path, 'rb') as f:
        diffs = unicode(f.read(), 'utf-8')
    changes = index_diffs(path, diffs)
    if changes:
        index = path + '.index'
        with open(index, 'wb') as idx:
            for n, line in changes:
                print>>idx, (u"%s:%s: %s" % (path, n, line)).encode('utf-8')
        print "%s: %d changes indexed in %s" % (path, len(changes), index)
    else:
        print "%s: no interesting changes" % (path,)

if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        write_index_for(path)
