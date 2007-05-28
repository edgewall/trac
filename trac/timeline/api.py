# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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

from urlparse import urljoin

from trac.core import *
from trac.util.datefmt import to_timestamp
from trac.web.href import Href


class TimelineEvent(object):
    """Group event related information.

    The first two properties are set in the constructor:

    provider: reference to the event provider

    kind: category of the event, will also be used as the CSS class for
          the event's entry in the timeline

    The following is set using the `add_markup` method.
    
    markup: dictionary of litteral informations regarding the events.
            Standard keys include:
             - 'title': short summary for the event
             - 'header': markup that comes before the main body
             - 'footer': markup that comes after the main body

    The next two are set using the `add_wiki` method.
    
    context: resource context
    wikitext: dictionary of contextual information
              Standard keys include:
              `body` will be interpreted as the main text
              `summary`

    The next four are set using the `set_changeinfo` method.
    
    date, author, authenticated, ipnr:
             date and authorship info for the event;
             `date` is a datetime instance

    Other properties:

    href_fragment: optional fragment that will position to some place
                   within the resource page

    direct_href: direct link to the event,, if there's no resource associated
                 to it
    """

    def __init__(self, *args, **kwargs):
        """`TimelineEvent(provider, kind)` creates an event.

        `provider` is the Component which provided the event and
        `kind` is the specific sub-type of this event.

        Note that 0.11dev API introduced originally another signature:
        `(self, kind, title='', href=None, markup=None)`
        We'll also stay compatible with the above until 0.12.
        """
        self.markup = {}
        self.wikitext = {}
        self.author = 'unknown'
        self.date = self.authenticated = self.ipnr = None
        self.context = None
        self.href_fragment = ''
        if isinstance(args[0], Component):
            self.provider = args[0]
            self.kind = args[1]
        else:
            self.kind = args[0]
            class DummyProvider(object):
                def event_formatter(self, event, key):
                    return ('oneliner', {'shorten': True})
            self.provider = DummyProvider()
            title = len(args) > 1 and args[1] or kwargs.get('title')
            href = len(args) > 2 and args[2] or kwargs.get('href')
            markup = len(args) > 3 and args[3] or kwargs.get('markup')
            self.direct_href = href
            if title:
                self.markup['title'] = title
            if markup:
                self.markup['header'] = markup

    def get_href(self, href=None):
        if self.context:
            return self.context.get_href(href) + self.href_fragment
        else:
            return self.direct_href

    def __repr__(self):
        return '<TimelineEvent %s - %r>' % (self.date,
                                            self.context or self.direct_href)

    def set_changeinfo(self, date, author='anonymous', authenticated=None,
                       ipnr=None):
        self.date = date
        self.author = author
        self.authenticated = authenticated
        self.ipnr = ipnr

    def add_markup(self, **kwargs):
        """Populate the markup dictionary."""
        for k, v in kwargs.iteritems():
            if v:
                self.markup[k] = v

    def add_wiki(self, context, **kwargs):
        """Populate the wikitext dictionary."""
        self.context = context
        for k, v in kwargs.iteritems():
            if v:
                self.wikitext[k] = v

    def dateuid(self):
        return to_timestamp(self.date)

    # What follows correspond to a temporary API used during 0.11dev
    # It's kept for compatibility but will be removed in 0.12, so don't use

    title = property(lambda s: s.markup.get('title'))
    href = property(get_href)
    def _get_abs_href(self):
        req = self.context.req
        if self.href.startswith('/'):
            # Convert from a relative `href` 
            return urljoin(req.abs_href.base, self.href)
        else:
            return self.href
    abs_href = property(fget=_get_abs_href)

    def set_context(self, context, wikitext=None):
        """Deprecated: use `add_wiki` instead"""
        self.add_wiki(context, body=wikitext)



class ITimelineEventProvider(Interface):
    """Extension point interface for adding sources for timed events to the
    timeline.
    """

    def get_timeline_filters(req):
        """Return a list of filters that this event provider supports.
        
        Each filter must be a (name, label) tuple, where `name` is the internal
        name, and `label` is a human-readable name for display.

        Optionally, the tuple can contain a third element, `checked`.
        If `checked` is omitted or True, the filter is active by default,
        otherwise it will be inactive.
        """

    def get_timeline_events(req, start, stop, filters):
        """Return a list of events in the time range given by the `start` and
        `stop` parameters.

        The `filters` parameters is a list of the enabled filters, each item
        being the name of the tuples returned by `get_timeline_filters`.

        Since 0.11, the events are TimelineEvent instances.

        Note:
        The events returned by this function used to be tuples of the form
        (kind, href, title, date, author, markup). This is now deprecated.
        """

    def event_formatter(event, wikitext_key):
        """For a given key (as found in the TimelineEvent.wikitext dictionary),
        specify which formatter flavor and options should be used.

        Returning `('oneliner', {})` is a safe choice and returning `None`
        will let the template decide.
        """
