# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2019 Edgewall Software
# Copyright (C) 2007 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

"""Sample Wiki syntax extension plugin."""

from trac.core import *
from trac.util.html import tag
from trac.util.text import shorten_line
from trac.versioncontrol.api import NoSuchChangeset, RepositoryManager
from trac.versioncontrol.web_ui import ChangesetModule
from trac.wiki.api import IWikiSyntaxProvider

revision = "$Rev$"
url = "$URL$"

class RevisionLinks(Component):
    """Adds a few more ways to refer to changesets."""

    implements(IWikiSyntaxProvider)

    KEYWORDS = ['[Rr]ev(?:ision)?', '[Cc]hangeset']

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        def revlink(f, match, fullmatch):
            elts = match.split()
            rev = elts[1] # ignore keyword
            reponame = ''
            if len(elts) > 2: # reponame specified
                reponame = elts[-1]
            return self._format_revision_link(f, 'revision', reponame, rev, rev,
                                              fullmatch)

        yield (r"!?(?:%s)\s+%s(?:\s+in\s+\w+)?" %
               ("|".join(self.KEYWORDS), ChangesetModule.CHANGESET_ID), revlink)

    def get_link_resolvers(self):
        def resolverev(f, ns, rev, label, fullmatch):
            return self._format_revision_link(f, ns, '', rev, label, fullmatch)
        yield ('revision', resolverev)

    def _format_revision_link(self, formatter, ns, reponame, rev, label,
                              fullmatch=None):
        rev, params, fragment = formatter.split_link(rev)
        try:
            repos = RepositoryManager(self.env).get_repository(reponame)
            if repos:
                changeset = repos.get_changeset(rev)
                return tag.a(label, class_="changeset",
                             title=shorten_line(changeset.message),
                             href=(formatter.href.changeset(rev) +
                                   params + fragment))
        except NoSuchChangeset:
            pass
        return tag.a(label, class_="missing changeset", rel="nofollow",
                     href=formatter.href.changeset(rev))
