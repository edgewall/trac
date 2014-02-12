# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2013 Edgewall Software
# Copyright (C) 2010 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

# Simple wrapper script needed to run epydoc

import sys

try:
    from epydoc.cli import cli
except ImportError:
    print>>sys.stderr, "No epydoc installed (see http://epydoc.sourceforge.net)"
    sys.exit(2)


# Epydoc 3.0.1 has some trouble running with recent Docutils (>= 0.6),
# so we work around this bug, following the lines of the fix in
# https://bugs.gentoo.org/attachment.cgi?id=210118
# (see http://bugs.gentoo.org/287546)

try:
    from docutils.nodes import Text
    if not hasattr(Text, 'data'):
        setattr(Text, 'data', property(lambda self: self.astext()))
except ImportError:
    print>>sys.stderr, "docutils is needed for running epydoc " \
        "(see http://docutils.sourceforge.net)"
    sys.exit(2)

# Epydoc doesn't allow much control over the generated graphs. This is
# bad especially for the class graph for Component which has a lot of
# subclasses, so we need to force Left-to-Right mode.

# from epydoc.docwriter.html import HTMLWriter
# HTMLWriter_render_graph = HTMLWriter.render_graph
# def render_graph_LR(self, graph):
#     if graph:
#         graph.body += 'rankdir=LR\n'
#     return HTMLWriter_render_graph(self, graph)
# HTMLWriter.render_graph = render_graph_LR

# Well, LR mode doesn't really look better...
# the ASCII-art version seems better in most cases.


# Workaround "visiting unknown node type" error due to `.. note ::`
# This was due to the lack of Admonitions transforms. Add it.

from epydoc.markup.restructuredtext import _DocumentPseudoWriter
from docutils.transforms import writer_aux

orig_get_transforms = _DocumentPseudoWriter.get_transforms
def pseudo_get_transforms(self):
    return orig_get_transforms(self) + [writer_aux.Admonitions]
_DocumentPseudoWriter.get_transforms = pseudo_get_transforms

# Run epydoc
cli()
