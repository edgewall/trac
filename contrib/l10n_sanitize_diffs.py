# Copyright (C) 2007-2012 Edgewall Software
# This file is distributed under the same license as the Trac project.

"""

L10N tool which takes a list of .po files containing conflict markers
and removes the conflicts which are only about differences in line
numbers.

This makes it easier to merge translation .po files across branches.
      
"""
import re

ignore_lineno_re = re.compile(r'''
         <<<<  .*\n
    ((?: \#    .*\n )+)   # \1 == comment only
         ====  .*\n
    ((?: \#    .*\n )+)   # \2 == comment only
         >>>>  .*\n
    ''', re.MULTILINE | re.VERBOSE)

def sanitize_file(path):
    with file(path, 'rb+') as f:
        sanitized, nsub = ignore_lineno_re.subn(r'\2', f.read())
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
