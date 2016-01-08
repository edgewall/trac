#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
# Copyright (C) 2006 Matthew Good <matt@matt-good.net>
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
# Author: Matthew Good <matt@matt-good.net>

import errno
import fileinput
from getpass import getpass
from hashlib import md5
from optparse import OptionParser
import sys


def ask_pass():
    pass1 = getpass('New password: ')
    pass2 = getpass('Re-type new password: ')
    if pass1 != pass2:
        print >>sys.stderr, "They don't match, sorry"
        sys.exit(1)
    return pass1

def get_digest(userprefix, password=None):
    if password == None:
        password = ask_pass()
    return make_digest(userprefix, password)

def make_digest(userprefix, password):
    return userprefix + md5(userprefix + password).hexdigest()

usage = "%prog [-c] [-b] passwordfile realm username"
parser = OptionParser(usage=usage)
parser.add_option('-c', action='store_true', dest='create', default=False,
                  help='Create a new file')
parser.add_option('-b', action='store_true', dest='batch', default=False,
                  help='Batch mode, password on the commandline.')

if len(sys.argv) <= 1:
    parser.print_help()
    sys.exit(1)

opts, args = parser.parse_args()

try:
    if opts.batch:
        filename, realm, username, password = args
    else:
        filename, realm, username = args
        password = None
except ValueError:
    parser.error('Wrong number of arguments')

prefix = '%s:%s:' % (username, realm)

if opts.create:
    try:
        f = open(filename, 'w')
    except EnvironmentError, e:
        if e.errno == errno.EACCES:
            print >>sys.stderr, 'Unable to update file', filename
            sys.exit(1)
        else:
            raise
    try:
        print >>f, get_digest(prefix, password)
    finally:
        f.close()
else:
    try:
        matched = False
        for line in fileinput.input(filename, inplace=True):
            if line.startswith(prefix):
                if not matched:
                    print get_digest(prefix, password)
                matched = True
            else:
                print line,
        if not matched:
            f = open(filename, 'a')
            try:
                print >>f, get_digest(prefix, password)
            finally:
                f.close()
    except EnvironmentError, e:
        if e.errno == errno.ENOENT:
            print >>sys.stderr, 'Could not open passwd file %s for reading.' \
                                % filename
            print >>sys.stderr, 'Use -c option to create a new one.'
            sys.exit(1)
        elif e.errno == errno.EACCES:
            print >>sys.stderr, 'Unable to update file', filename
            sys.exit(1)
        else:
            raise
