#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2016-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.

"""This tool help diagnose basic flaws in Jinja2 templates.

It tries to present useful hints to the template developer, in
particular to help resolve nesting issues.

"""

import argparse
import glob
import io
import re
import sys

from pkg_resources import parse_version as pv
from collections import namedtuple
from os.path import abspath, dirname, join, normpath


# Setup XHTML validation

etree = None

def setup_html():
    global etree
    try:
        from lxml import etree
    except ImportError:
        print("can't validate the XHTML parts in Jinja2 templates"
              " (no lxml installed)")

    if etree and pv(etree.__version__) < pv('2.0.0'):
        # 2.0.7 and 2.1.x are known to work.
        print("can't validate the XHTML parts in Jinja2 templates"
              " (lxml < 2.0, api incompatibility)")

    if etree:
        # Note: this code derived from trac/tests/functional (FIXME)

        class Resolver(etree.Resolver):
            # ./contrib/jinjachecker.py # <- we live here
            # ./trac/tests/functional/  # <- there are the DTDs
            contrib_dir = dirname(abspath(__file__))
            base_dir = normpath(join(contrib_dir, '../trac/tests/functional'))

            def resolve(self, system_url, public_id, context):
                filename = join(self.base_dir, system_url.split("/")[-1])
                return self.resolve_filename(filename, context)
        parser = etree.XMLParser(dtd_validation=True)
        parser.resolvers.add(Resolver())
        etree.set_default_parser(parser)
    return etree


# -- Common ----------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="""\
        If no flags are given, both jinja and html checks will be performed.

        An alternative usage is to run the tool via make, i.e. `make jinja`,
        which  will run the tool on all .html files.
        """)
    parser.add_argument('templates', nargs='+', metavar='TEMPLATE',
                        help="path or glob of template(s) to check")
    parser.add_argument('-j', '--jinja-only', action='store_true', dest='jinja',
                        help="only check the jinja structure")
    parser.add_argument('--html-only', action='store_true', dest='html',
                        help="only validate the HTML")
    parser.add_argument('-q', '--quiet', action='store_true',
                        help="""don't show the filtered content, only the
                        errors""")
    parser.add_argument('-i', '--show-ignored', action='store_true',
                        dest='ignored',
                        help="""show ignored XHTML errors and HTML hints""")
    args = parser.parse_args()
    status = 0
    only = 'jinja' if args.jinja else ('html' if args.html else None)
    setup_html()
    for arg in args.templates:
        for template in glob.glob(arg):
            status += analyze(template, only, args.quiet, args.ignored)
    if status > 0:
        print("One error found." if status == 1 else
              "%d errors found." % status)
    else:
        print("No errors.")
    return 1 if status > 0 else 0


def analyze(jinja_template, only=None, quiet=False, show_ignored=False):
    """Analyzes a Jinja2 template, its control structure as well as the
    structure of the HTML.
    """
    with open(jinja_template, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    line_statements, html, html_hints = scan(lines)
    issues_j = issues_h = 0
    if only != 'html':
        issues_j = check_jinja(jinja_template, line_statements, quiet)
        report_errors('Jinja2', issues_j)
    if only != 'jinja' and etree and jinja_template.endswith('.html'):
        issues_h = check_html(jinja_template, html, html_hints, quiet,
                              show_ignored)
        report_errors('HTML', issues_h)
    return issues_j + issues_h


def report_errors(kind, issues):
    if issues:
        print('# -- %s %d errors' % (kind, issues))
    else:
        print('# -- %s OK' % kind)



# -- Jinja2 ----------------------------------------------------------------

# Jinja2 Syntax
#
# Note: keep in sync with trac/web/chrome.py

BLOCK_START_STRING = '{{'
BLOCK_END_STRING = '}}'

COMMENT_START_STRING = '{#'
COMMENT_END_STRING = '#}'

LINE_STATEMENT_PREFIX = '#'
LINE_COMMENT_PREFIX = '##'

JINJA2_BLOCK_KEYWORDS = (
    'block', 'call', 'for', 'if', 'macro', 'raw', 'trans', 'with'
)

JINJA2_NO_COLON_KEYWORDS = (
    'block', 'do', 'extends', 'import', 'include', 'macro', 'pluralize', 'set',
    'trans', 'with'
)

JINJA2_NO_EXPRESSION_KEYWORDS = ('else', 'pluralize', 'trans', 'with')

StatementTuple = namedtuple('StatementTuple',
                            ('linenum', 'indent', 'end', 'kw', 'expr', 'colon'))

class Statement(StatementTuple):
    def __new__(cls, *args, **kwargs):
        self = super(Statement, cls).__new__(cls, *args, **kwargs)
        self.is_block = (self.kw in JINJA2_BLOCK_KEYWORDS or
                         self.kw == 'set' and '=' not in self.expr)
        return self

LINE_STATEMENT_RE = re.compile(r'^(\s*)%s-?(\s*)(end)?(\w+)(.*?)?(:)?$' %
                               LINE_STATEMENT_PREFIX)

STATEMENT_RE = re.compile(r'^(\s*)(.*)\s*$')

JINJACHECK_RE = re.compile(r'jinjacheck(?:er)?: "([^"]+)" OK')


def scan(lines):
    """Scans template lines and separates Jinja2 structure from HTML structure.
    """

    def count_parens(line):
        return line.count('(') - line.count(')')

    def process_multiline_expr(expr, open_parens=0):
        open_parens += count_parens(expr)
        if open_parens:
            linenum, line = lines.next()
            m = STATEMENT_RE.match(line)
            line_statements.append(
                Statement(linenum, len(m.group(1)), '', '', m.group(2), ''))
            process_multiline_expr(line.rstrip(), open_parens)

    lines = iter(enumerate(lines, 1))
    get_line = lambda: next(lines)
    line_statements = []
    html = []
    html_hints = []
    def check_for_hint(linenum, comment):
        m = JINJACHECK_RE.search(comment)
        if m:
            html_hints.append((linenum, m.group(1)))
    try:
        comment_start = -1 # not in a comment
        html_start = start_idx = end_idx = 0
        linenum, line = get_line()
        html_line = []
        while True:
            # skip empty lines
            if comment_start > -1:
                # we're in a comment block, look for the end of block
                end_idx = line.find(COMMENT_END_STRING, end_idx)
                check_for_hint(linenum, line[comment_start:end_idx])
                if end_idx > -1:
                    # found, we're no longer in a comment
                    comment_start = -1
                    # look for another comment block on the *same* line
                    html_start = start_idx = end_idx + 2
                    continue
                else:
                    # comment block continues on next line
                    comment_start = end_idx = 0
            else:
                # look for start of a comment block
                start_idx = line.find(COMMENT_START_STRING, start_idx)
                frag = line[html_start:start_idx]
                if start_idx > -1:
                    # found, we're a the start of a comment
                    html_line.append(frag)
                    # look for the end of this comment block on *same* line
                    comment_start = end_idx = start_idx + 2
                    continue
                else:
                    if html_start >= 2:
                        # we ended a comment without starting a new one
                        html_line.append(frag)
                    else:
                        # look for start of comment line
                        if line.strip().startswith(LINE_COMMENT_PREFIX):
                            check_for_hint(linenum, line)
                        else:
                            # check for a line statement
                            m = LINE_STATEMENT_RE.match(line)
                            if m:
                                expr = m.group(5)
                                line_statements.append(
                                    Statement(linenum, (len(m.group(1)) +
                                                        len(m.group(2)) + 1),
                                              m.group(3) or '', m.group(4),
                                              expr, m.group(6) or ''))
                                process_multiline_expr(expr)
                            else:
                                html_line = line
            html.append((linenum, ''.join(html_line).rstrip()))
            linenum, line = get_line()
            html_line = []
            html_start = start_idx = end_idx = 0
    except StopIteration:
        return line_statements, html, html_hints


def check_jinja(filename, line_statements, quiet):
    """Verifies proper nesting of Jinja2 control structures.
    """
    print("\n# -- Jinja2 check for '%s'" % filename)
    kw_stack = []
    issues = 0
    for s in line_statements:
        warn = []
        top = kw_stack and kw_stack[-1]
        if s.end:
            if not s.is_block:
                warn.append("'end%s' is not a valid keyword" % s.kw)
            else:
                if top:
                    if s.kw == top.kw:
                        kw_stack.pop()
                    else:
                        warn.append(("'end%s' misplaced, current block is"
                                     " '%s' (at line %d)") %
                                    (s.kw, top.kw, top.linenum))
                else:
                    warn.append("'end%s' misplaced, not in a block" % s.kw)
            if s.expr:
                if s.kw == 'block':
                    if top and top.expr != s.expr:
                        warn.append(("'endblock %s' misplaced or misspelled,"
                                     " current block is '%s %s'") %
                                    (s.expr, top.kw, top.expr))
                else:
                    warn.append("no expression allowed for 'end%s' statement"
                                % s.kw)
            if s.colon:
                warn.append("no ending colon wanted for 'end%s' statement"
                            % s.kw)
        else:
            if s.is_block:
                kw_stack.append(s)
            if s.expr == '' and s.kw not in JINJA2_NO_EXPRESSION_KEYWORDS:
                warn.append("expression missing in '%s' statement" % s.kw)
            if s.kw in JINJA2_NO_COLON_KEYWORDS:
                if s.colon:
                    warn.append("no ending colon wanted for '%s' statement"
                                % s.kw)
            elif s.kw and not s.colon:
                warn.append("ending colon wanted for '%s' statement" % s.kw)
            if s.kw in ('elif', 'else'):
                if not top or not top.kw == 'if':
                    warn.append("'%s' is not inside an 'if' block" % s.kw)
        issues += len(warn)
        print_statement(filename, s, warn, quiet)
    while kw_stack:
        issues += 1
        s = kw_stack.pop()
        fake = Statement(line_statements[-1].linenum + 1, *[None] * 5)
        print_statement(filename, fake,
                        ["'end%s' statement missing for '%s' at line %d)" %
                         (s.kw, s.kw, s.linenum)], quiet=True)
    return issues


def print_statement(filename, s, warn=None, quiet=False):
    if not quiet:
        print('%5d %s %s%s%s%s' % (s.linenum,
                                   ' ' * s.indent,
                                   '}' if s.end else
                                   '{' if s.is_block else ' ',
                                   s.kw.upper(), s.expr, s.colon))
    while warn:
        print('%s:%s: %s' % (filename, s.linenum, warn.pop()))


# -- HTML ------------------------------------------------------------------

XHTML_DOCTYPE = '''<!DOCTYPE html \
    PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" \
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'''

IGNORED_XHTML_ERRORS = [
    ('Element style does not carry attribute type',
     '<style> without "type" attribute'),
    ('Element script does not carry attribute type',
     '<script> without "type" attribute'),
    ]


def check_html(filename, html_lines, html_hints, quiet, show_ignored):
    """Validates the given HTML (as XHTML actually)
    """
    global etree
    print("\n# -- HTML check for '%s'" % filename)
    # re-build the page content, replacing the DTD with the XHTML DTD,
    # or adding it if missing. Jinja2 expressions are removed.
    opened_braces = 0
    normalized_lines = []
    has_html_elt = has_head_elt = has_body_elt = False
    for linenum, line in html_lines:
        has_html_elt = has_html_elt or '<html>' in line
        has_head_elt = has_head_elt or '<head>' in line
        has_body_elt = has_body_elt or '<body>' in line
        if line.strip() != '<!DOCTYPE html>':
            normalized, opened_braces = remove_jinja_exprs(linenum, line,
                                                           opened_braces)
            normalized_lines.append(normalized)
    is_xml = html_lines[0][1].startswith('<?xml ')
    if not is_xml:
        if not has_body_elt:
            normalized_lines[0] = '<body>' + normalized_lines[0]
            normalized_lines[-1] = normalized_lines[-1] + '</body>'
        if not has_head_elt:
            normalized_lines[0] = '<head><title/></head>' + normalized_lines[0]
        if not has_html_elt:
            normalized_lines[0] = '<html>' + normalized_lines[0]
            normalized_lines[-1] = normalized_lines[-1] + '</html>'
        normalized_lines[0] = XHTML_DOCTYPE + normalized_lines[0]
    page = '\n'.join(normalized_lines)
    ## print('LINES %s' % ''.join("%5d: %s" % l for l in html_lines)) # DEBUG
    ## print('PAGE %s' %
    ##       '\n'.join("%5d: %s" % l for l in enumerate(normalized_lines)))
    ## print('HINTS', repr(html_hints)) # DEBUG
    etree.clear_error_log()
    try:
        # lxml will try to convert the URL to unicode by itself,
        # this won't work for non-ascii URLs, so help him
        etree.parse(io.StringIO(page), base_url='.') #  base_url ??
        if not quiet:
            for lineinfo in html_lines:
                print('%5d %s' % lineinfo),
        return 0
    except etree.XMLSyntaxError as e:
        errors = []
        for entry in e.error_log:
            errors.append((entry.line, entry.column, entry.message))
        real_errors = []
        def process_error(linenum, col, msg):
            hint_linenum = hint = ignored = None
            for e, comment in IGNORED_XHTML_ERRORS:
                if e == msg:
                    ignored = ' (IGNORED "%s")' % comment
                    break
            if not ignored:
                while html_hints:
                    hint_linenum, hint = html_hints[0]
                    if hint_linenum >= linenum or len(html_hints) == 1:
                        break
                    del html_hints[0]
                if hint and hint in msg:
                    del html_hints[0]
                    ignored = ' (IGNORED "%s")' % hint
            if not ignored:
                real_errors.append(linenum)
                ignored = ''
            if not ignored or show_ignored:
                print('%s:%s:%s: %s%s'
                      % (filename, linenum, col, msg, ignored))
        for linenum, line in html_lines:
            if not quiet:
                print('%5d %s' % (linenum, line)),
            while errors and errors[0][0] == linenum:
                err = errors[0]
                del errors[0]
                process_error(*err)
        # in case some errors haven't been flushed at this point...
        for err in errors:
            process_error(*err)
        return len(real_errors)


BRACES_RE = re.compile(r'(?:\b(id|for|selected|checked)=")?\$?([{}])')

def remove_jinja_exprs(linenum, line, opened_braces):
    """This probably could be a one-liner... ;-)
    """
    idx = 0
    line = line.replace('$', '')
    spans = []
    if opened_braces:
        spans.append([0, len(line), False])
    while True:
        m = BRACES_RE.search(line, idx)
        if m:
            idx = m.start(2)
            if line[idx] == '{':
                opened_braces += 1
                if opened_braces == 1:
                    spans.append([idx, len(line), m.group(1)])
            else:
                opened_braces -= 1
                if opened_braces == 0:
                    spans[-1][1] = idx
            idx += 1
        else:
            break
    normalized = ''
    pos = 0
    for start, end, attr in spans:
        if start > pos:
            normalized += line[pos:start]
        ## normalized += '@((%s))@' % line[start:end + 1] # DEBUG
        if attr in ('id', 'for'):
            normalized += "L%d-%d" % (linenum, start)
        elif attr in ('selected', 'checked'):
            normalized += attr
        pos = end + 1
    if pos < len(line):
        normalized += line[pos:]
    return normalized, opened_braces

if __name__ == '__main__':
    sys.exit(main())
