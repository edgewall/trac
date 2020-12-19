#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2020 Edgewall Software
# Copyright (C) 2006 Matthew Good <matt@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Matthew Good <matt@matt-good.net>

import argparse
import errno
import fileinput
import getpass
import hashlib
import sys

from trac.util.text import printerr


def ask_pass():
    pass1 = getpass.getpass('New password: ')
    pass2 = getpass.getpass('Re-type new password: ')
    if pass1 != pass2:
        printerr("htdigest: password verification error")
        sys.exit(1)
    return pass1


def get_digest(userprefix, password=None):
    if password is None:
        password = ask_pass()
    return make_digest(userprefix, password)


def make_digest(userprefix, password):
    value = (userprefix + password).encode('utf-8')
    return userprefix + hashlib.md5(value).hexdigest()


def main():
    """
    %(prog)s [-c] passwordfile realm username
    %(prog)s -b[c] passwordfile realm username password\
    """
    parser = argparse.ArgumentParser(usage=main.__doc__)
    parser.add_argument('-b', action='store_true', dest='batch',
                        help="batch mode; password is passed on the command "
                             "line IN THE CLEAR")
    parser.add_argument('-c', action='store_true', dest='create',
                        help="create a new htdigest file, overwriting any "
                             "existing file")
    parser.add_argument('passwordfile', help=argparse.SUPPRESS)
    parser.add_argument('realm', help=argparse.SUPPRESS)
    parser.add_argument('username', help=argparse.SUPPRESS)
    parser.add_argument('password', nargs='?', help=argparse.SUPPRESS)

    args = parser.parse_args()
    if args.batch and args.password is None:
        parser.error("too few arguments")
    elif not args.batch and args.password is not None:
        parser.error("too many arguments")

    prefix = '%s:%s:' % (args.username, args.realm)
    if args.create:
        try:
            with open(args.passwordfile, 'w', encoding='utf-8') as f:
                print(get_digest(prefix, args.password), file=f)
        except EnvironmentError as e:
            if e.errno == errno.EACCES:
                printerr("Unable to update file %s" % args.passwordfile)
                sys.exit(1)
            else:
                raise
    else:
        matched = False
        try:
            for line in fileinput.input(args.passwordfile, inplace=True):
                if line.startswith(prefix):
                    if not matched:
                        print(get_digest(prefix, args.password))
                    matched = True
                else:
                    print(line.rstrip())
            if not matched:
                with open(args.passwordfile, 'a', encoding='utf-8') as f:
                    print(get_digest(prefix, args.password), file=f)
        except EnvironmentError as e:
            if e.errno == errno.ENOENT:
                printerr("Could not open password file %s for reading. "
                         "Use -c option to create a new one."
                         % args.passwordfile)
                sys.exit(1)
            elif e.errno == errno.EACCES:
                printerr("Unable to update file %s" % args.passwordfile)
                sys.exit(1)
            else:
                raise


if __name__ == '__main__':
    main()
