"""Sample Wiki syntax extension plugin."""

from genshi.builder import tag

from trac.core import *
from trac.util.text import shorten_line
from trac.versioncontrol.api import NoSuchChangeset
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
            rev = match.split(' ', 1)[1] # ignore keyword
            return self._format_revision_link(f, 'revision', rev, rev,
                                              fullmatch)

        yield (r"!?(?:%s)\s+%s" % ("|".join(self.KEYWORDS),
                                   ChangesetModule.CHANGESET_ID),
               revlink)

    def get_link_resolvers(self):
        yield ('revision', self._format_revision_link)

    def _format_revision_link(self, formatter, ns, rev, label, fullmatch=None):
        rev, params, fragment = formatter.split_link(rev)
        try:
            changeset = self.env.get_repository().get_changeset(rev)
            return tag.a(label, class_="changeset",
                         title=shorten_line(changeset.message),
                         href=(formatter.href.changeset(rev) +
                               params + fragment))
        except NoSuchChangeset:
            return tag.a(label, class_="missing changeset",
                         href=formatter.href.changeset(rev),
                         rel="nofollow")
