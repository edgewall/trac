# Copyright (C) 2013 Edgewall Software
# This file is distributed under the same license as the Trac project.

"""

L10N tool which takes a list of .po in conflicted state and revert
ignorable changes.

It resolve the conflicts for which "theirs" changes consist solely of
line number changes, by reverting to the working copy content.

This makes it easier to merge translation .po files across branches.

"""

import re

ignore_lineno_re = re.compile(r'''
          <<<< .* \n
    ( (?: [^=] .* \n )+)   # \1 == "working copy"
          ==== .* \n
    ( (?: \#   .* \n )+)   # \2 == comment only for "theirs"
          >>>> .* \n
    ''', re.MULTILINE | re.VERBOSE)

def sanitize_file(path):
    with file(path, 'rb+') as f:
        sanitized, nsub = ignore_lineno_re.subn(r'\1', f.read())
        if nsub:
            print("reverted %d ignorable changes in %s" % (nsub, path))
            f.seek(0)
            f.write(sanitized)
            f.truncate()
        else:
            print("no ignorable changes in %s" % (path,))

if __name__ == '__main__':
    import sys
    for path in sys.argv[1:]:
        sanitize_file(path)
