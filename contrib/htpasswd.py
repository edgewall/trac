#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2018 Edgewall Software
# Copyright (C) 2008 Eli Carter
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import getpass
import optparse
import sys

from trac.util import salt
from trac.util.compat import crypt, wait_for_file_mtime_change
from trac.util.text import printerr, printout

if crypt is None:
    printerr("The crypt module is not found. Install the passlib package "
             "from PyPI.", newline=True)
    sys.exit(1)


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
        with open(self.filename, 'r') as f:
            for line in f:
                username, pwhash = line.split(':')
                entry = [username, pwhash.rstrip()]
                self.entries.append(entry)

    def save(self):
        """Write the htpasswd file to disk"""
        wait_for_file_mtime_change(self.filename)
        with open(self.filename, 'w') as f:
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
        %prog [-c] filename username
        %prog -b[c] filename username password
        %prog -D filename username
    """
    # For now, we only care about the use cases that affect tests/functional.py
    parser = optparse.OptionParser(usage=main.__doc__)
    parser.add_option('-b', action='store_true', dest='batch', default=False,
        help='Batch mode; password is passed on the command line IN THE CLEAR.'
        )
    parser.add_option('-c', action='store_true', dest='create', default=False,
        help='Create a new htpasswd file, overwriting any existing file.')
    parser.add_option('-D', action='store_true', dest='delete_user',
        default=False, help='Remove the given user from the password file.')

    if len(sys.argv) <= 1:
        parser.print_help()
        sys.exit(1)

    options, args = parser.parse_args()

    def syntax_error(msg):
        """Utility function for displaying fatal error messages with usage
        help.
        """
        printerr("Syntax error: " + msg, newline=True)
        printerr(parser.format_help(), newline=True)
        sys.exit(1)

    # Non-option arguments
    if len(args) < 2:
        syntax_error("Insufficient number of arguments.\n")
    filename, username = args[:2]
    password = None
    if options.delete_user:
        if len(args) != 2:
            syntax_error("Incorrect number of arguments.\n")
    else:
        if len(args) == 3 and options.batch:
            password = args[2]
        elif len(args) == 2 and not options.batch:
            first = getpass.getpass("New password:")
            second = getpass.getpass("Re-type new password:")
            if first == second:
                password = first
            else:
                printout("htpasswd: password verification error")
                return
        else:
            syntax_error("Incorrect number of arguments.\n")

    try:
        passwdfile = HtpasswdFile(filename, create=options.create)
    except IOError:
        syntax_error("File not found.\n")
    else:
        if options.delete_user:
            passwdfile.delete(username)
        else:
            passwdfile.update(username, password)
        passwdfile.save()


if __name__ == '__main__':
    main()
