#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os.path
import sys

from babel.core import negotiate_locale
from babel.messages.pofile import read_po, write_po


class ScriptError(StandardError):
    pass


def _is_fuzzy(message):
    return u'fuzzy' in message.flags


def _has_msgstr(message):
    msgstrs = message.string
    if not isinstance(msgstrs, (list, tuple)):
        msgstrs = [msgstrs]
    return any(v for v in msgstrs)


def _open_pofile(filename):
    with open(filename, 'rb') as f:
        return read_po(f)


def _get_domains():
    return sorted(name[:-4]
                  for name in os.listdir(os.path.join('trac', 'locale'))
                  if name.endswith('.pot'))


def _get_locales(domain):
    def has_pofile(name):
        return os.path.isfile(os.path.join('trac', 'locale', name,
                                           'LC_MESSAGES', domain + '.po'))
    return sorted(name for name in os.listdir(os.path.join('trac', 'locale'))
                       if has_pofile(name))


def main(args):
    try:
        domain, source_file = args
    except:
        raise ScriptError('Usage: %s DOMAIN POFILE' %
                          os.path.basename(sys.argv[0]))
    domains = _get_domains()
    locales = _get_locales(domain)
    if not domains:
        raise ScriptError('No trac/locale/*.pot files.')
    if domain not in domains:
        raise ScriptError('Domain parameter should be one of %s.' %
                          ', '.join(domains))
    if not locales:
        raise ScriptError('No trac/locale/*/LC_MESSAGES/*.po files.')
    source = _open_pofile(source_file)
    preferred_locales = [value.split(None, 1)[0]
                         for value in (source.locale and str(source.locale),
                                       source.language_team)
                         if value]
    locale = negotiate_locale(preferred_locales, locales)
    if not locale or locale == 'en_US':
        sys.stderr.write('No available *.po file for %s.\n' %
                         ', '.join(preferred_locales))
        return 1
    target_file = os.path.join('trac', 'locale', locale, 'LC_MESSAGES',
                               domain + '.po')
    target = _open_pofile(target_file)
    pot = _open_pofile(os.path.join('trac', 'locale', domain + '.pot'))
    n = 0
    for source_msg in source:
        msgid = source_msg.id
        if msgid == '':
            continue
        if not _has_msgstr(source_msg):
            continue
        if msgid in target:
            target_msg = target[msgid]
        elif msgid in pot:
            target_msg = pot[msgid]
        else:
            continue
        if target_msg.string == source_msg.string:
            continue
        if not _has_msgstr(source_msg):
            continue
        if _has_msgstr(target_msg) and not _is_fuzzy(target_msg):
            continue
        if msgid not in target:
            target_msg = target_msg.clone()
            target[msgid] = target_msg
        target_msg.string = source_msg.string
        target_msg.flags = source_msg.flags
        n += 1
    if n > 0:
        with open(target_file, 'w') as f:
            write_po(f, target)
            del f
        print('Merged %d messages from %s and updated %s' % (n, source_file,
                                                             target_file))
    else:
        print('Merged no messages from %s' % source_file)


if __name__ == '__main__':
    try:
        rc = main(sys.argv[1:])
    except ScriptError as e:
        rc = 1
        sys.stderr.write('%s\n' % e)
    sys.exit(rc or 0)
