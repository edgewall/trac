# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2003-2006 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2006 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2007 Christian Boos <cboos@neuf.fr>
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
#         Christian Boos <cboos@neuf.fr>

import re

from trac.core import *
from trac.notification import EMAIL_LOOKALIKE_PATTERN

class WikiParser(Component):
    """wiki subsystem dedicated to the Wiki text parsing."""

    # Some constants used for clarifying the Wiki regexps:

    BOLDITALIC_TOKEN = "'''''"
    BOLD_TOKEN = "'''"
    ITALIC_TOKEN = "''"
    UNDERLINE_TOKEN = "__"
    STRIKE_TOKEN = "~~"
    SUBSCRIPT_TOKEN = ",,"
    SUPERSCRIPT_TOKEN = r"\^"
    INLINE_TOKEN = "`"
    STARTBLOCK_TOKEN = r"\{\{\{"
    STARTBLOCK = "{{{"
    ENDBLOCK_TOKEN = r"\}\}\}"
    ENDBLOCK = "}}}"
    
    LINK_SCHEME = r"[\w.+-]+" # as per RFC 2396
    INTERTRAC_SCHEME = r"[a-zA-Z.+-]*?" # no digits (support for shorthand links)

    QUOTED_STRING = r"'[^']+'|\"[^\"]+\""

    SHREF_TARGET_FIRST = r"[\w/?!#@](?<!_)" # we don't want "_"
    SHREF_TARGET_MIDDLE = r"(?:\|(?=[^|\s])|[^|<>\s])"
    SHREF_TARGET_LAST = r"[\w/=](?<!_)" # we don't want "_"

    LHREF_RELATIVE_TARGET = r"[/#][^\s\]]*|\.\.?(?:[/#][^\s\]]*)?"

    XML_NAME = r"[\w:](?<!\d)[\w:.-]*?" # See http://www.w3.org/TR/REC-xml/#id 

    # Sequence of regexps used by the engine

    _pre_rules = [
        # Font styles
        r"(?P<bolditalic>!?%s)" % BOLDITALIC_TOKEN,
        r"(?P<bold>!?%s)" % BOLD_TOKEN,
        r"(?P<italic>!?%s)" % ITALIC_TOKEN,
        r"(?P<underline>!?%s)" % UNDERLINE_TOKEN,
        r"(?P<strike>!?%s)" % STRIKE_TOKEN,
        r"(?P<subscript>!?%s)" % SUBSCRIPT_TOKEN,
        r"(?P<superscript>!?%s)" % SUPERSCRIPT_TOKEN,
        r"(?P<inlinecode>!?%s(?P<inline>.*?)%s)" \
        % (STARTBLOCK_TOKEN, ENDBLOCK_TOKEN),
        r"(?P<inlinecode2>!?%s(?P<inline2>.*?)%s)" \
        % (INLINE_TOKEN, INLINE_TOKEN)]

    # Rules provided by IWikiSyntaxProviders will be inserted here

    _post_rules = [
        # e-mails
        r"(?P<email>!?%s)" % EMAIL_LOOKALIKE_PATTERN,
        # > ...
        r"(?P<citation>^(?P<cdepth>>(?: *>)*))",
        # &, < and > to &amp;, &lt; and &gt;
        r"(?P<htmlescape>[&<>])",
        # wiki:TracLinks
        r"(?P<shref>!?((?P<sns>%s):(?P<stgt>%s|%s(?:%s*%s)?)))" \
        % (LINK_SCHEME, QUOTED_STRING,
           SHREF_TARGET_FIRST, SHREF_TARGET_MIDDLE, SHREF_TARGET_LAST),
        # [wiki:TracLinks with optional label] or [/relative label]
        (r"(?P<lhref>!?\[(?:"
         r"(?P<rel>%s)|" % LHREF_RELATIVE_TARGET + # ./... or /...
         r"(?P<lns>%s):(?P<ltgt>%s|[^\]\s]*))" % \
         (LINK_SCHEME, QUOTED_STRING) + # wiki:TracLinks or wiki:"trac links"
         r"(?:\s+(?P<label>%s|[^\]]+))?\])" % QUOTED_STRING), # optional label
        # [[macro]] call
        (r"(?P<macro>!?\[\[(?P<macroname>[\w/+-]+)"
         r"(\]\]|\((?P<macroargs>.*?)\)\]\]))"),
        # == heading == #hanchor
        r"(?P<heading>^\s*(?P<hdepth>=+)\s.*\s(?P=hdepth)\s*"
        r"(?P<hanchor>#%s)?(?:\s|$))" % XML_NAME,
        #  * list
        r"(?P<list>^(?P<ldepth>\s+)(?:[-*]|\d+\.|[a-zA-Z]\.|[ivxIVX]{1,5}\.) )",
        # definition:: 
        r"(?P<definition>^\s+((?:%s[^%s]*%s|%s(?:%s{,2}[^%s])*?%s|[^%s%s:]|:[^:])+::)(?:\s+|$))"
        % (INLINE_TOKEN, INLINE_TOKEN, INLINE_TOKEN,
           STARTBLOCK_TOKEN, ENDBLOCK[0], ENDBLOCK[0], ENDBLOCK_TOKEN,
           INLINE_TOKEN, STARTBLOCK[0]),
        # (leading space)
        r"(?P<indent>^(?P<idepth>\s+)(?=\S))",
        # || table ||
        r"(?P<last_table_cell>\|\|\s*$)",
        r"(?P<table_cell>\|\|)"]

    _processor_re = re.compile('#\!([\w+-][\w+-/]*)')
    _processor_param_re = re.compile(r'''(\w+)=(".*?"|'.*?'|\w+)''')
    _anchor_re = re.compile('[^\w:.-]+', re.UNICODE)

    def __init__(self):
        self._compiled_rules = None
        self._link_resolvers = None
        self._helper_patterns = None
        self._external_handlers = None

    def _get_rules(self):
        self._prepare_rules()
        return self._compiled_rules
    rules = property(_get_rules)

    def _get_helper_patterns(self):
        self._prepare_rules()
        return self._helper_patterns
    helper_patterns = property(_get_helper_patterns)

    def _get_external_handlers(self):
        self._prepare_rules()
        return self._external_handlers
    external_handlers = property(_get_external_handlers)

    def _prepare_rules(self):
        from trac.wiki.api import WikiSystem
        if not self._compiled_rules:
            helpers = []
            handlers = {}
            syntax = self._pre_rules[:]
            i = 0
            for resolver in WikiSystem(self.env).syntax_providers:
                for regexp, handler in resolver.get_wiki_syntax():
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

    def _get_link_resolvers(self):
        if not self._link_resolvers:
            from trac.wiki.api import WikiSystem
            resolvers = {}
            for resolver in WikiSystem(self.env).syntax_providers:
                for namespace, handler in resolver.get_link_resolvers():
                    resolvers[namespace] = handler
            self._link_resolvers = resolvers
        return self._link_resolvers
    link_resolvers = property(_get_link_resolvers)

    def parse(self, wikitext):
        """Parse `wikitext` and produce a WikiDOM tree."""
        # obviously still some work to do here ;)
        return wikitext

