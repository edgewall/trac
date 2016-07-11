#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
# Copyright (C) 2013 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

"""

L10N tool which copies all msgid to the msgstr.

This can be useful to verify the actual changes in the en_UK message
catalogs.

"""

import re


msgid_msgstr_re = re.compile(r'''
    (                                             # \1 "en_US"
                                          \r?\n
                msgid \s ".*"             \r?\n
        (?: (?: msgid_plural \s )? ".*"   \r?\n
        )*
    )
    (                                             # \2 "en_GB"
                msgstr.* \s ".*"          \r?\n
        (?: (?: msgstr.* \s )? ".*"       \r?\n
        )*                                \r?\n
    )
    ''', re.MULTILINE | re.VERBOSE)

def reset_file(path):
    with open(path, 'rb+') as f:
        eol = '\r\n'
        content = f.read()
        if eol not in content:
            eol = '\n'
        def reset_msgstr(m):
            msgid, msgstr = m.groups()
            if '\nmsgid_plural' in msgid:
                msgstr = (msgid
                          .replace(eol + 'msgid_plural', eol + 'msgstr[1]')
                          .replace(eol + 'msgid', 'msgstr[0]'))
            else:
                msgstr = msgid.replace(eol + 'msgid', 'msgstr')
            return msgid + msgstr + eol
        sanitized, nsub = msgid_msgstr_re.subn(reset_msgstr, content)
        if nsub:
            print("reset %d messages to en_US in %s" % (nsub, path))
            f.seek(0)
            f.write(sanitized)
            f.truncate()
        else:
            print("no messages found in %s" % (path,))


if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        reset_file(path)
