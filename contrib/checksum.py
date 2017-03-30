#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import hashlib
import io
import sys


def main():
    args = sys.argv[1:]
    if not args:
        sys.stderr.write('Usage: %s algorithm files...\n' % sys.argv[0])
        return 2
    algorithms = args.pop(0).replace(':', ' ').split()
    for algorithm in algorithms:
        for filename in args:
            m = hashlib.new(algorithm)
            with io.open(filename, 'rb') as f:
                while True:
                    data = f.read(4096)
                    if not data:
                        break
                    m.update(data)
            print('%s *%s' % (m.hexdigest(), filename))

if __name__ == '__main__':
    sys.exit(main() or 0)
