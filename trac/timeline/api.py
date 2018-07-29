# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2006 Christian Boos <cboos@edgewall.org>
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

        The events are `(kind, date, author, data)` tuples, where `kind`
        is a string used for categorizing the event, `date` is a `datetime`
        object, `author` is a string and `data` is some private data that
        the component will reuse when rendering the event.

        When the event has been created indirectly by another module,
        like this happens when calling `AttachmentModule.get_timeline_events()`
        the tuple can also specify explicitly the provider by returning tuples
        of the following form: `(kind, date, author, data, provider)`.
        """

    def render_timeline_event(context, field, event):
        """Display the title of the event in the given context.

        :param context: the `RenderingContext` object that can be used for
                        rendering
        :param field: what specific part information from the event should
                      be rendered: can be the 'title', the 'description' or
                      the 'url'
        :param event: the event tuple, as returned by `get_timeline_events`
        """
