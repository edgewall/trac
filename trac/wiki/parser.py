# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2003-2006 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2006 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2007 Christian Boos <cboos@edgewall.org>
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
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>
#         Christian Boos <cboos@edgewall.org>

import re

from trac.core import *
from trac.notification import EMAIL_LOOKALIKE_PATTERN


class WikiParser(Component):
    """Wiki text parser."""

    # Some constants used for clarifying the Wiki regexps:

    BOLDITALIC_TOKEN = "'''''"
    BOLD_TOKEN = "'''"
    BOLD_TOKEN_WIKICREOLE = r"\*\*"
    ITALIC_TOKEN = "''"
    ITALIC_TOKEN_WIKICREOLE = "//"
    UNDERLINE_TOKEN = "__"
    STRIKE_TOKEN = "~~"
    SUBSCRIPT_TOKEN = ",,"
    SUPERSCRIPT_TOKEN = r"\^"
    INLINE_TOKEN = "`" # must be a single char (see P<definition> below)
    STARTBLOCK_TOKEN = r"\{\{\{"
    STARTBLOCK = "{{{"
    ENDBLOCK_TOKEN = r"\}\}\}"
    ENDBLOCK = "}}}"
    BULLET_CHARS = u"-*\u2022"

    LINK_SCHEME = r"[a-zA-Z][-a-zA-Z0-9+._]*" # as per RFC 2396 + '_'
    INTERTRAC_SCHEME = r"[a-zA-Z.+-]*?" # no digits (for shorthand links)

    QUOTED_STRING = r"'[^']+'|\"[^\"]+\""

    SHREF_TARGET_FIRST = r"[\w/?!#@](?<!_)" # we don't want "_"
    SHREF_TARGET_MIDDLE = r"(?:\|(?=[^|\s])|[^|<>\s])"
    SHREF_TARGET_LAST = r"[\w/=](?<!_)" # we don't want "_"

    def _lhref_relative_target(sep):
        return r"[/\?#][^%s\]]*|\.\.?(?:[/\?#][^%s\]]*)?" % (sep, sep)

    LHREF_RELATIVE_TARGET = _lhref_relative_target(r'\s')

    XML_NAME = r"[\w:](?<!\d)[\w:.-]*?" # See http://www.w3.org/TR/REC-xml/#id

    PROCESSOR = r"(\s*)#\!([\w+-][\w+-/]*)"
    PROCESSOR_PARAM = r'''(?P<proc_pname>[-\w]+)''' \
                      r'''=(?P<proc_pval>".*?"|'.*?'|[-\w]+)'''

    def _set_anchor(name, sep):
        return r'=#(?P<anchorname>%s)(?:%s(?P<anchorlabel>[^\]]*))?' % \
               (name, sep)

    # Sequence of regexps used by the engine

    _pre_rules = [
        # Font styles
        r"(?P<bolditalic>!?%s)" % BOLDITALIC_TOKEN,
        r"(?P<bold>!?%s)" % BOLD_TOKEN,
        r"(?P<bold_wc>!?%s)" % BOLD_TOKEN_WIKICREOLE,
        r"(?P<italic>!?%s)" % ITALIC_TOKEN,
        r"(?P<italic_wc>!?%s)" % ITALIC_TOKEN_WIKICREOLE,
        r"(?P<underline>!?%s)" % UNDERLINE_TOKEN,
        r"(?P<strike>!?%s)" % STRIKE_TOKEN,
        r"(?P<subscript>!?%s)" % SUBSCRIPT_TOKEN,
        r"(?P<superscript>!?%s)" % SUPERSCRIPT_TOKEN,
        r"(?P<inlinecode>!?%s(?P<inline>.*?)%s)" \
        % (STARTBLOCK_TOKEN, ENDBLOCK_TOKEN),
        r"(?P<inlinecode2>!?%s(?P<inline2>.*?)%s)" \
        % (INLINE_TOKEN, INLINE_TOKEN),
        ]

    # Rules provided by IWikiSyntaxProviders will be inserted here

    _post_rules = [
        # WikiCreole line breaks
        r"(?P<linebreak_wc>!?\\\\)",
        # e-mails
        r"(?P<email>!?%s)" % EMAIL_LOOKALIKE_PATTERN,
        # <wiki:Trac bracket links>
        r"(?P<shrefbr>!?<(?P<snsbr>%s):(?P<stgtbr>[^>]+)>)" % LINK_SCHEME,
        # &, < and > to &amp;, &lt; and &gt;
        r"(?P<htmlescape>[&<>])",
        # wiki:TracLinks or intertrac:wiki:TracLinks
        r"(?P<shref>!?((?P<sns>%s):(?P<stgt>%s:(?:%s)|%s|%s(?:%s*%s)?)))" \
        % (LINK_SCHEME, LINK_SCHEME, QUOTED_STRING, QUOTED_STRING,
           SHREF_TARGET_FIRST, SHREF_TARGET_MIDDLE, SHREF_TARGET_LAST),
        # [wiki:TracLinks with optional label] or [/relative label]
        (r"(?P<lhref>!?\[(?:"
         r"(?P<rel>%s)|" % LHREF_RELATIVE_TARGET + # ./... or /...
         r"(?P<lns>%s):(?P<ltgt>%s:(?:%s)|%s|[^\]\s\%s]*))" % \
         (LINK_SCHEME, LINK_SCHEME, QUOTED_STRING, QUOTED_STRING, u'\u200b') +
         # wiki:TracLinks or wiki:"trac links" or intertrac:wiki:"trac links"
         r"(?:[\s%s]+(?P<label>%s|[^\]]*))?\])" % \
         (u'\u200b', QUOTED_STRING)), # trailing space, optional label
        # [=#anchor] creation
        r"(?P<anchor>!?\[%s\])" % _set_anchor(XML_NAME, r'\s+'),
        # [[macro]] call or [[WikiCreole link]]
        (r"(?P<macrolink>!?\[\[(?:[^]]|][^]])+\]\])"),
        # == heading == #hanchor
        r"(?P<heading>^\s*(?P<hdepth>={1,6})\s(?P<htext>.*?)"
        r"(?P<hanchor>#%s)?\s*$)" % XML_NAME,
        #  * list
        r"(?P<list>^(?P<ldepth>\s*)"
        ur"(?:[%s]|(?P<lstart>[0-9]+|[a-zA-Z]|[ivxIVX]{1,5})\.)\s)"
        % (BULLET_CHARS),
        # definition::
        r"(?P<definition>^\s+"
        r"((?:%s[^%s]*%s|%s(?:%s{,2}[^%s])*?%s|[^%s%s:]|:[^:])+::)(?:\s+|$))"
        % (INLINE_TOKEN, INLINE_TOKEN, INLINE_TOKEN,
           STARTBLOCK_TOKEN, ENDBLOCK[0], ENDBLOCK[0], ENDBLOCK_TOKEN,
           INLINE_TOKEN, STARTBLOCK[0]),
        # |- row separator
        r"(?P<table_row_sep>!?\s*\|-+\s*"
        r"(?P<table_row_params>%s\s*)*)" % PROCESSOR_PARAM,
        # (leading space)
        r"(?P<indent>^(?P<idepth>\s+)(?=\S))",
        # || table ||
        r"(?P<table_cell>!?(?P<table_cell_sep>=?(?:\|\|)+=?)"
        r"(?P<table_cell_last>\s*\\?$)?)",
        ]

    _processor_re = re.compile(PROCESSOR)
    _startblock_re = re.compile(r"\s*%s(?:%s|\s*$)" %
                                (STARTBLOCK, PROCESSOR))
    _processor_param_re = re.compile(PROCESSOR_PARAM)
    _anchor_re = re.compile(r'[^\w:.-]+', re.UNICODE)

    _macro_re = re.compile(r'''
        (?P<macroname> [\w/+-]+ \?? | \? )     # macro, macro? or ?
          (?: \( (?P<macroargs> .*? ) \) )? $  # optional arguments within ()
    ''', re.VERBOSE)

    _creolelink_re = re.compile(r'''
        (?:
          (?P<rel> %(rel)s )                # rel is "./..." or "/..."
        | (?: (?P<lns> %(scheme)s ) : )?    # lns is the optional "scheme:"
            (?P<ltgt>                       # ltgt is the optional target
              %(scheme)s : (?:%(quoted)s)   #   - "scheme:'...quoted..'"
            | %(quoted)s                    #   - "'...quoted...'"
            | [^|]+                         #   - anything but a '|'
            )?
        )
        \s* (?: \| (?P<label> .* ) )?       # optional label after a '|'
        $
        ''' % {'rel': _lhref_relative_target(r'|'),
               'scheme': LINK_SCHEME,
               'quoted': QUOTED_STRING}, re.VERBOSE)

    _set_anchor_wc_re = re.compile(_set_anchor(XML_NAME, r'\|\s*') + r'$')

    def __init__(self):
        self._compiled_rules = None
        self._link_resolvers = None
        self._helper_patterns = None
        self._external_handlers = None

    @property
    def rules(self):
        self._prepare_rules()
        return self._compiled_rules

    @property
    def helper_patterns(self):
        self._prepare_rules()
        return self._helper_patterns

    @property
    def external_handlers(self):
        self._prepare_rules()
        return self._external_handlers

    def _prepare_rules(self):
        from trac.wiki.api import WikiSystem
        if not self._compiled_rules:
            helpers = []
            handlers = {}
            syntax = self._pre_rules[:]
            i = 0
            for resolver in WikiSystem(self.env).syntax_providers:
                for regexp, handler in resolver.get_wiki_syntax() or []:
                    handlers['i' + str(i)] = handler
                    syntax.append('(?P<i%d>%s)' % (i, regexp))
                    i += 1
            syntax += self._post_rules[:]
            helper_re = re.compile(r'\?P<([a-z\d_]+)>')
            for rule in syntax:
                helpers += helper_re.findall(rule)[1:]
            rules = re.compile('(?:' + '|'.join(syntax) + ')', re.UNICODE)
            self._external_handlers = handlers
            self._helper_patterns = helpers
            self._compiled_rules = rules

    @property
    def link_resolvers(self):
        if not self._link_resolvers:
            from trac.wiki.api import WikiSystem
            resolvers = {}
            for resolver in WikiSystem(self.env).syntax_providers:
                for namespace, handler in resolver.get_link_resolvers() or []:
                    resolvers[namespace] = handler
            self._link_resolvers = resolvers
        return self._link_resolvers

    def parse(self, wikitext):
        """Parse `wikitext` and produce a WikiDOM tree."""
        # obviously still some work to do here ;)
        return wikitext


_processor_pname_re = re.compile(r'[-\w]+$')


def parse_processor_args(processor_args):
    """Parse a string containing parameter assignments,
    and return the corresponding dictionary.

    Isolated keywords are interpreted as `bool` flags, `False` if the keyword
    is prefixed with "-", `True` otherwise.

    >>> parse_processor_args('ab="c de -f gh=ij" -')
    {'ab': 'c de -f gh=ij'}

    >>> sorted(parse_processor_args('ab=c de -f gh="ij klmn"').items())
    [('ab', 'c'), ('de', True), ('f', False), ('gh', 'ij klmn')]

    >>> args = 'data-name=foo-bar data-true -data-false'
    >>> sorted(parse_processor_args(args).items())
    [('data-false', False), ('data-name', 'foo-bar'), ('data-true', True)]
    """
    args = WikiParser._processor_param_re.split(processor_args)
    keys = [str(k) for k in args[1::3]] # used as keyword parameters
    values = [v[1:-1] if v[:1] + v[-1:] in ('""', "''") else v
              for v in args[2::3]]
    for flags in args[::3]:
        for flag in flags.strip().split():
            if _processor_pname_re.match(flag):
                if flag[0] == '-':
                    if len(flag) > 1:
                        keys.append(str(flag[1:]))
                        values.append(False)
                else:
                    keys.append(str(flag))
                    values.append(True)
    return dict(zip(keys, values))
