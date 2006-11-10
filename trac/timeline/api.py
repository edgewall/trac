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

from trac.core import *
from trac.util.datefmt import to_timestamp


class TimelineEvent(object):
    """Group event related information.

    title:   short summary for the event
    href:    relative link to resource advertised by this event
    markup:  optional Markup that should be taken into account along side the
             contextual information
    date, author, authenticated, ipnr:
             date and authorship info for the event;
             `date` is a datetime instance
    type, id, message:
             context and contextual information;
             `message` will be interpreted as wiki text
    """

    def __init__(self, kind, title='', href=None, markup=None):
        self.kind = kind
        self.title = title
        self.href = href
        self.markup = markup
        self.author = 'unknown'
        self.date = self.authenticated = self.ipnr = None
        self.type = self.id = self.message = None

    def __repr__(self):
        return '<TimelineEvent %s - %s>' % (self.date, self.href)

    def set_changeinfo(self, date,
                       author='anonymous', authenticated=None, ipnr=None):
        self.date = date
        self.author = author
        self.authenticated = authenticated
        self.ipnr = ipnr

    def set_context(self, type, id, message=None):
        self.type = type
        self.id = id
        self.message = message

    def dateuid(self):
        return to_timestamp(self.date),


class ITimelineEventProvider(Interface):
    """Extension point interface for adding sources for timed events to the
    timeline.
    """

    def get_timeline_filters(self, req):
        """Return a list of filters that this event provider supports.
        
        Each filter must be a (name, label) tuple, where `name` is the internal
        name, and `label` is a human-readable name for display.

        Optionally, the tuple can contain a third element, `checked`.
        If `checked` is omitted or True, the filter is active by default,
        otherwise it will be inactive.
        """

    def get_timeline_events(self, req, start, stop, filters):
        """Return a list of events in the time range given by the `start` and
        `stop` parameters.
        
        The `filters` parameters is a list of the enabled filters, each item
        being the name of the tuples returned by `get_timeline_filters`.

        The events are TimelineEvent instances.

        Note:
        The events returned by this function used to be tuples of the form
        (kind, href, title, date, author, message). This is now deprecated.
        """
