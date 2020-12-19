#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2020 Edgewall Software
# Copyright (C) 2008 Eli Carter
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

import argparse
import getpass
import sys

from trac.util import salt
from trac.util.compat import crypt, wait_for_file_mtime_change
from trac.util.text import printerr

if crypt is None:
    printerr("The crypt module is not found. Install the passlib package "
             "from PyPI.", newline=True)
    sys.exit(1)


def ask_pass():
    pass1 = getpass.getpass('New password: ')
    pass2 = getpass.getpass('Re-type new password: ')
    if pass1 != pass2:
        printerr("htpasswd: password verification error")
        sys.exit(1)
    return pass1


class HtpasswdFile(object):
    """A class for manipulating htpasswd files."""

    def __init__(self, filename, create=False):
        self.entries = []
        self.filename = filename
        if not create:
            self.load()

    def load(self):
        """Read the htpasswd file into memory."""
        self.entries = []
        with open(self.filename, 'r', encoding='utf-8') as f:
            for line in f:
                username, pwhash = line.split(':')
                entry = [username, pwhash.rstrip()]
                self.entries.append(entry)

    def save(self):
        """Write the htpasswd file to disk"""
        wait_for_file_mtime_change(self.filename)
        with open(self.filename, 'w', encoding='utf-8') as f:
            f.writelines("%s:%s\n" % (entry[0], entry[1])
                         for entry in self.entries)

    def update(self, username, password):
        """Replace the entry for the given user, or add it if new."""
        pwhash = crypt(password, salt())
        matching_entries = [entry for entry in self.entries
                            if entry[0] == username]
        if matching_entries:
            matching_entries[0][1] = pwhash
        else:
            self.entries.append([username, pwhash])

    def delete(self, username):
        """Remove the entry for the given user."""
        self.entries = [entry for entry in self.entries
                        if entry[0] != username]


def main():
    """
    %(prog)s [-c] passwordfile username
    %(prog)s -b[c] passwordfile username password
    %(prog)s -D passwordfile username\
    """

    parser = argparse.ArgumentParser(usage=main.__doc__)
    parser.add_argument('-b', action='store_true', dest='batch',
                        help="batch mode; password is passed on the command "
                             "line IN THE CLEAR")
    parser_group = parser.add_mutually_exclusive_group()
    parser_group.add_argument('-c', action='store_true', dest='create',
                              help="create a new htpasswd file, overwriting "
                                   "any existing file")
    parser_group.add_argument('-D', action='store_true', dest='delete_user',
                              help="remove the given user from the password "
                                   "file")
    parser.add_argument('passwordfile', help=argparse.SUPPRESS)
    parser.add_argument('username', help=argparse.SUPPRESS)
    parser.add_argument('password', nargs='?', help=argparse.SUPPRESS)

    args = parser.parse_args()
    password = args.password
    if args.delete_user:
        if password is not None:
            parser.error("too many arguments")
    else:
        if args.batch and password is None:
            parser.error("too few arguments")
        elif not args.batch and password is not None:
            parser.error("too many arguments")

    try:
        passwdfile = HtpasswdFile(args.passwordfile, create=args.create)
    except EnvironmentError:
        printerr("File not found.")
        sys.exit(1)
    else:
        if args.delete_user:
            passwdfile.delete(args.username)
        else:
            if password is None:
                password = ask_pass()
            passwdfile.update(args.username, password)
        passwdfile.save()


if __name__ == '__main__':
    main()
