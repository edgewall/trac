# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2018 Edgewall Software
# Copyright (C) 2008 Noah Kantrowitz <noah@coderanger.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

# Trac documentation build configuration file, created by
# sphinx-quickstart on Wed May 14 09:05:13 2008.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# The contents of this file are pickled, so don't put values in the
# namespace that aren't pickleable (module imports are okay, they're
# removed automatically).
#
# All configuration values have a default value; values that are
# commented out serve to show the default value.

import os
import sys
from datetime import datetime

from trac.util import get_pkginfo

pkg_info = get_pkginfo(sys.modules['trac'])

# General substitutions.
project = 'Trac'
copyright = '%s, Edgewall Software' % datetime.now().year
url = pkg_info['home_page']

# The default replacements for |version| and |release|, also used in various
# other places throughout the built documents.
#
# The short X.Y version.
version = pkg_info['version'].split('dev')[0]
# The full version, including alpha/beta/rc tags.
release = pkg_info['version']

# Devel or Release mode for the documentation (if devel, include TODOs,
# can also be used in conditionals: .. ifconfig :: devel)
devel = 'dev' in pkg_info['version']

# If your extensions are in another directory, add it here. If the
# directory is relative to the documentation root, use os.path.abspath
# to make it absolute, like shown here.
# sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# General configuration
# ---------------------

# Add any Sphinx extension module names here, as strings.
# They can be extensions coming with Sphinx (named 'sphinx.ext.*')
# or your custom ones.

extensions = []

# -- Autodoc

extensions.append('sphinx.ext.autodoc')

autoclass_content = 'both'
autodoc_member_order = 'bysource'

# -- Conditional content (see setup() below)
extensions.append('sphinx.ext.ifconfig')

# -- Link to other Sphinx documentations
extensions.append('sphinx.ext.intersphinx')

intersphinx_mapping = {'python': ('https://docs.python.org/2.7', None)}

# -- Keep track of :todo: items
extensions.append('sphinx.ext.todo')

todo_include_todos = devel

# -- PDF support via http://code.google.com/p/rst2pdf/
try:
    import rst2pdf
    extensions.append('rst2pdf.pdfbuilder')
except ImportError:
    pass

# -- Documentation coverage (`make apidoc-coverage`)
extensions.append('sphinx.ext.coverage')

coverage_skip_undoc_in_source = True


# Add any paths that contain templates here, relative to this directory.
#templates_path = ['utils/templates']

# The suffix of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'


# There are two options for replacing |today|: either, you set today to some
# non-false value, then it is used:
#today = ''
# Else, today_fmt is used as the format for a strftime call.
today_fmt = '%B %d, %Y'

# List of documents that shouldn't be included in the build.
unused_docs = []

# List of directories, relative to source directories, that shouldn't be searched
# for source files.
exclude_patterns = [
]

# If true, '()' will be appended to :func: etc. cross-reference text.
#add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
#add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
#show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'trac'

# The default role is a reference to some Python object
default_role = 'py:obj'


# Options for HTML output
# -----------------------

# The style sheet to use for HTML and HTML Help pages. A file of that name
# must exist either in Sphinx' static/ path, or in one of the custom paths
# given in html_static_path.
html_style = 'tracsphinx.css'

html_theme = 'sphinxdoc'

html_theme_options = {
#    'linkcolor': '#B00',
#    'visitedlinkcolor': '#B00',
}


# The name for this set of Sphinx documents.  If None, it defaults to
# "<project> v<release> documentation".
#html_title = None

# The name of an image file (within the static path) to place at the top of
# the sidebar.
html_logo = 'images/trac_logo.png'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['utils/']

# If not '', a 'Last updated on:' timestamp is inserted at every page bottom,
# using the given strftime format.
html_last_updated_fmt = '%b %d, %Y'

# If true, SmartyPants will be used to convert quotes and dashes to
# typographically correct entities.
#html_use_smartypants = True

# Custom sidebar templates, maps document names to template names.
#html_sidebars = {}

# Additional templates that should be rendered to pages, maps page names to
# template names.
#html_additional_pages = {}

# If false, no module index is generated.
html_use_modindex = True

# If true, the reST sources are included in the HTML build as _sources/<name>.
#html_copy_source = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it.  The value of this option must be the
# base URL from which the finished HTML is served.
#html_use_opensearch = ''

# If nonempty, this is the file name suffix for HTML files (e.g. ".xhtml").
#html_file_suffix = ''

# Output file base name for HTML help builder.
htmlhelp_basename = 'Tracdoc'


modindex_common_prefix = ['trac.', 'tracopt.']


# Options for LaTeX output
# ------------------------

# The paper size ('letter' or 'a4').
#latex_paper_size = 'letter'

# The font size ('10pt', '11pt' or '12pt').
#latex_font_size = '10pt'

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, document class [howto/manual]).
latex_documents = [
  ('index', 'Trac.tex', 'Trac API Documentation', 'The Trac Team', 'manual'),
]

# The name of an image file (relative to this directory) to place at the top of
# the title page.
#latex_logo = None

# For "manual" documents, if this is true, then toplevel headings are parts,
# not chapters.
#latex_use_parts = False

# Additional stuff for the LaTeX preamble.
#latex_preamble = ''

# Documents to append as an appendix to all manuals.
#latex_appendices = []

# If false, no module index is generated.
#latex_use_modindex = True



# Options for PDF output
# ----------------------
# (initially copied from
#  http://rst2pdf.googlecode.com/svn/tags/0.16/doc/manual.txt)

# Grouping the document tree into PDF files. List of tuples
# (source start file, target name, title, author, options).
#
# If there is more than one author, separate them with \\.
# For example: r'Guido van Rossum\\Fred L. Drake, Jr., editor'
#
# The options element is a dictionary that lets you override
# this config per-document.
# For example,
# ('index', u'MyProject', u'My Project', u'Author Name',
#  dict(pdf_compressed = True))
# would mean that specific document would be compressed
# regardless of the global pdf_compressed setting.

pdf_documents = [
    ('index', 'trac_dev', project, u'The Trac Team'),
]

# A comma-separated list of custom stylesheets (latest has higher precedence)
pdf_stylesheets = [
    'sphinx',
    'a4',
    'trac',
    os.path.join(os.path.dirname(__file__), 'utils', 'trac_dev_pdf.style')
]

# Create a compressed PDF
# Use True/False or 1/0
# Example: compressed=True
pdf_compressed = True

# A colon-separated list of folders to search for fonts. Example:
# pdf_font_path = ['/usr/share/fonts', '/usr/share/texmf-dist/fonts/']

# Language to be used for hyphenation support
pdf_language = "en_US"

# Mode for literal blocks wider than the frame. Can be
# overflow, shrink or truncate
pdf_fit_mode = "shrink"

# Section level that forces a break page.
# For example: 1 means top-level sections start in a new page
# 0 means disabled
pdf_break_level = 1

# When a section starts in a new page, force it to be 'even', 'odd',
# or just use 'any'
#pdf_breakside = 'any'

# Insert footnotes where they are defined instead of
# at the end.
#pdf_inline_footnotes = True

# verbosity level. 0 1 or 2
#pdf_verbosity = 0

# If false, no index is generated.
pdf_use_index = True

# If false, no modindex is generated.
pdf_use_modindex = True

# If false, no coverpage is generated.
#pdf_use_coverpage = True

# Name of the cover page template to use
#pdf_cover_template = 'sphinxcover.tmpl'

# Documents to append as an appendix to all manuals.
#pdf_appendices = []

# Enable experimental feature to split table cells. Use it
# if you get "DelayedTable too big" errors
#pdf_splittables = False

# Set the default DPI for images
#pdf_default_dpi = 72

# Enable rst2pdf extension modules (default is only vectorpdf)
# you need vectorpdf if you want to use sphinx's graphviz support
#pdf_extensions = ['vectorpdf']

# Page template name for "regular" pages
#pdf_page_template = 'cutePage'

# Show Table Of Contents at the beginning?
#pdf_use_toc = True

# How many levels deep should the table of contents be?
pdf_toc_depth = 9999

# Add section number to section references
pdf_use_numbered_links = False

# Background images fitting mode
pdf_fit_background_mode = 'scale'

def setup(app):
    # adding role for linking to InterTrac targets on t.e.o
    from docutils import nodes
    from docutils.parsers.rst import roles

    def teo_role(name, rawtext, text, lineno, inliner, options={}, content=[]):
        # special case ticket references
        if text[0] == '#':
            ref = url + '/ticket/' + text[1:]
        else:
            ref = url + '/intertrac/' + text
        roles.set_classes(options)
        node = nodes.reference(rawtext, text, refuri=ref, **options)
        return [node], []
    roles.register_canonical_role('teo', teo_role)

    def extensionpoints_role(name, rawtext, text, lineno, inliner, options={},
                             content=[]):
        ref = url + '/wiki/TracDev/PluginDevelopment/ExtensionPoints/' + text
        roles.set_classes(options)
        node = nodes.reference(rawtext, text + " extension point",
                               refuri=ref, **options)
        return [node], []
    roles.register_canonical_role('extensionpoints', extensionpoints_role)

    # ifconfig variables
    app.add_config_value('devel', True, '')
