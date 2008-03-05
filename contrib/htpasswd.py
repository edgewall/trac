#!/usr/bin/python
"""Replacement for htpasswd"""

import os
import random
try:
    import crypt
except ImportError:
    import fcrypt as crypt
from optparse import OptionParser


def salt():
    """Returns a string of 2 randome letters"""
    # FIXME: Additional characters may be legal here.
    letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return random.choice(letters) + random.choice(letters)


class HtpasswdFile:
    def __init__(self, filename, create=False):
        self.entries = []
        self.filename = filename
        if not create:
            if os.path.exists(self.filename):
                self.load()
            else:
                raise Exception("%s does not exist" % self.filename)

    def load(self):
        lines = open(self.filename, 'r').readlines()
        self.entries = []
        for line in lines:
            username, hash = line.split(':')
            entry = [username, hash.rstrip()]
            self.entries.append(entry)

    def save(self):
        open(self.filename, 'w').writelines(["%s:%s\n" % (entry[0], entry[1]) for entry in self.entries])

    def update(self, username, password):
        hash = crypt.crypt(password, salt())
        matching_entries = [entry for entry in self.entries if entry[0] == username]
        if matching_entries:
            matching_entries[0][1] = hash
        else:
            self.entries.append([username, hash])

    def delete(self, username):
        self.entries = [entry for entry in self.entries if entry[0] != username]

def main():
    """%prog [-c] -b filename username password
    Create or update an htpasswd file"""
    # For now, we only care about the use cases that affect tests/functional.py
    parser = OptionParser(usage=main.__doc__)
    parser.add_option('-b', action='store_true', dest='batch', default=False,
        help='Batch mode; password is passed on the command line IN THE CLEAR.')
    parser.add_option('-c', action='store_true', dest='create', default=False,
        help='Create a new htpasswd file, overwriting any existing file.')
    parser.add_option('-D', action='store_true', dest='delete_user', default=False,
        help='Remove the given user from the password file.')

    options, args = parser.parse_args()

    assert(options.batch) # We only support batch mode for now.

    # Non-option arguments
    filename, username = args[:2]
    if options.delete_user:
        password = None
    else:
        password = args[2]

    passwdfile = HtpasswdFile(filename, create=options.create)

    if options.delete_user:
        passwdfile.delete(username)
    else:
        passwdfile.update(username, password)

    passwdfile.save()


if __name__ == '__main__':
    main()
