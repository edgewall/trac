# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import time
import unittest

from trac.timeline.web_ui import TimelineModule
from trac.wiki.tests import formatter

TIMELINE_TEST_CASES = u"""
============================== timeline: link resolver
timeline:2008-01-29
timeline:2008-01-29T15:48
timeline:2008-01-29T15:48Z
timeline:2008-01-29T16:48+01
timeline:2008-01-0A
timeline:@datestr_libc@
------------------------------
<p>
<a class="timeline" href="/timeline?from=2008-01-29T00%3A00%3A00Z" title="See timeline at 2008-01-29T00:00:00Z">timeline:2008-01-29</a>
<a class="timeline" href="/timeline?from=2008-01-29T15%3A48%3A00Z&amp;precision=minutes" title="See timeline at 2008-01-29T15:48:00Z">timeline:2008-01-29T15:48</a>
<a class="timeline" href="/timeline?from=2008-01-29T15%3A48%3A00Z&amp;precision=minutes" title="See timeline at 2008-01-29T15:48:00Z">timeline:2008-01-29T15:48Z</a>
<a class="timeline" href="/timeline?from=2008-01-29T15%3A48%3A00Z&amp;precision=seconds" title="See timeline at 2008-01-29T15:48:00Z">timeline:2008-01-29T16:48+01</a>
<a class="timeline missing" title="&#34;2008-01-0A&#34; is an invalid date, or the date format is not known. Try &#34;YYYY-MM-DDThh:mm:ss±hh:mm&#34; instead.">timeline:2008-01-0A</a>
<a class="timeline missing" title="&#34;@datestr_libc@&#34; is an invalid date, or the date format is not known. Try &#34;YYYY-MM-DDThh:mm:ss±hh:mm&#34; instead.">timeline:@datestr_libc@</a>
</p>
------------------------------
"""


def suite():
    suite = unittest.TestSuite()
    datestr_libc = time.strftime('%x', (2013, 10, 24, 0, 0, 0, 0, 0, -1))
    suite.addTest(formatter.suite(TIMELINE_TEST_CASES.replace('@datestr_libc@',
                                                              datestr_libc),
                                  file=__file__))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
