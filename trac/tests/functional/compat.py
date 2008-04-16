#!/usr/bin/python
import os
import shutil

# Closing FDs not supported with subprocess on Windows
close_fds = True
if os.name == 'nt':
    close_fds = False # not supported :(

# On Windows, shutil.rmtree doesn't remove files with the read-only
# attribute set, so this function explicitly removes it on every error
# before retrying.  Even on Linux, shutil.rmtree chokes on read-only
# directories, so we use this version in all cases.
# Fix from http://bitten.edgewall.org/changeset/521
def rmtree(root):
    """Catch shutil.rmtree failures on Windows when files are read-only."""
    def _handle_error(fn, path, excinfo):
        os.chmod(path, 0666)
        fn(path)
    return shutil.rmtree(root, onerror=_handle_error)

