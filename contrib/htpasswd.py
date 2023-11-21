#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2023 Edgewall Software
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

try:
    import passlib
except ImportError:
    passlib = None
    try:
        import crypt
    except ImportError:
        crypt = None
else:
    crypt = None

from trac.util.compat import wait_for_file_mtime_change
from trac.util.text import printerr


if passlib:
    from passlib.context import CryptContext
    _crypt_schemes = {
        'sha256': 'sha256_crypt',
        'sha512': 'sha512_crypt',
        'md5': 'apr_md5_crypt',
        'des': 'des_crypt',
    }
    from passlib.hash import bcrypt
    try:
        bcrypt.get_backend()
    except passlib.exc.MissingBackendError:
        pass
    else:
        _crypt_schemes['bcrypt'] = 'bcrypt'
    _crypt_context = CryptContext(schemes=sorted(_crypt_schemes.values()))
    _hash_methods = sorted(_crypt_schemes)
    def hash_password(word, method):
        scheme = _crypt_schemes[method]
        if hasattr(_crypt_context, 'hash'):  # passlib 1.7+
            hash_ = _crypt_context.hash
        else:
            hash_ = _crypt_context.encrypt
        return hash_(word, scheme=scheme)
elif crypt:
    _crypt_methods = {
        'sha256': crypt.METHOD_SHA256,
        'sha512': crypt.METHOD_SHA512,
        'md5': None,  # use md5crypt
        'des': crypt.METHOD_CRYPT,
    }
    if hasattr(crypt, 'METHOD_BLOWFISH'):
        _crypt_methods['bcrypt'] = crypt.METHOD_BLOWFISH
    _hash_methods = sorted(_crypt_methods)
    from trac.util import salt, md5crypt
    def hash_password(word, method):
        if method == 'md5':
            return md5crypt(word, salt(), '$apr1$')
        else:
            return crypt.crypt(word, crypt.mksalt(_crypt_methods[method]))
else:
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

    def update(self, username, password, method):
        """Replace the entry for the given user, or add it if new."""
        pwhash = hash_password(password, method)
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
    parser.add_argument('-t', dest='method', choices=_hash_methods,
                        default='md5', help='hash method for passwords '
                                            '(default: %(default)s)')
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
            passwdfile.update(args.username, password, args.method)
        passwdfile.save()


if __name__ == '__main__':
    main()
