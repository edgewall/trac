# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2006 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2005-2006 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Matthew Good <trac@matt-good.net>

from __future__ import with_statement

from cStringIO import StringIO
import csv
import errno
import functools
import inspect
from itertools import izip, tee
import locale
import os.path
from pkg_resources import find_distributions
import random
import re
import shutil
import sys
import struct
import tempfile
from urllib import quote, unquote, urlencode

from .compat import any, md5, sha1, sorted
from .datefmt import time_now, to_datetime, to_timestamp, utc
from .text import exception_to_unicode, to_unicode, getpreferredencoding


def get_reporter_id(req, arg_name=None):
    """Get most informative "reporter" identity out of a request.

    That's the `Request`'s authname if not 'anonymous', or a `Request`
    argument, or the session name and e-mail, or only the name or only
    the e-mail, or 'anonymous' as last resort.

    :param req: a `trac.web.api.Request`
    :param arg_name: if given, a `Request` argument which may contain
      the id for non-authentified users
    """
    if req.authname != 'anonymous':
        return req.authname
    if arg_name:
        r = req.args.get(arg_name)
        if r:
            return r
    name = req.session.get('name', None)
    email = req.session.get('email', None)
    if name and email:
        return '%s <%s>' % (name, email)
    return name or email or req.authname # == 'anonymous'


def content_disposition(type=None, filename=None):
    """Generate a properly escaped Content-Disposition header."""
    type = type or ''
    if filename is not None:
        if isinstance(filename, unicode):
            filename = filename.encode('utf-8')
        if type:
            type += '; '
        type += 'filename=' + quote(filename, safe='')
    return type


# -- os utilities

if os.name == 'nt':
    from getpass import getuser
else:
    import pwd
    def getuser():
        """Retrieve the identity of the process owner"""
        try:
            return pwd.getpwuid(os.geteuid())[0]
        except KeyError:
            return 'unknown'

try:
    WindowsError = WindowsError
except NameError:
    class WindowsError(OSError):
        """Dummy exception replacing WindowsError on non-Windows platforms"""


can_rename_open_file = False
if os.name == 'nt':
    _rename = lambda src, dst: False
    _rename_atomic = lambda src, dst: False

    try:
        import ctypes
        MOVEFILE_REPLACE_EXISTING = 0x1
        MOVEFILE_WRITE_THROUGH = 0x8
        MoveFileEx = ctypes.windll.kernel32.MoveFileExW

        def _rename(src, dst):
            if not isinstance(src, unicode):
                src = unicode(src, sys.getfilesystemencoding())
            if not isinstance(dst, unicode):
                dst = unicode(dst, sys.getfilesystemencoding())
            if _rename_atomic(src, dst):
                return True
            return MoveFileEx(src, dst, MOVEFILE_REPLACE_EXISTING
                                        | MOVEFILE_WRITE_THROUGH)

        CreateTransaction = ctypes.windll.ktmw32.CreateTransaction
        CommitTransaction = ctypes.windll.ktmw32.CommitTransaction
        MoveFileTransacted = ctypes.windll.kernel32.MoveFileTransactedW
        CloseHandle = ctypes.windll.kernel32.CloseHandle
        can_rename_open_file = True

        def _rename_atomic(src, dst):
            ta = CreateTransaction(None, 0, 0, 0, 0, 10000, 'Trac rename')
            if ta == -1:
                return False
            try:
                return (MoveFileTransacted(src, dst, None, None,
                                           MOVEFILE_REPLACE_EXISTING
                                           | MOVEFILE_WRITE_THROUGH, ta)
                        and CommitTransaction(ta))
            finally:
                CloseHandle(ta)
    except Exception:
        pass

    def rename(src, dst):
        # Try atomic or pseudo-atomic rename
        if _rename(src, dst):
            return
        # Fall back to "move away and replace"
        try:
            os.rename(src, dst)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise
            old = "%s-%08x" % (dst, random.randint(0, sys.maxint))
            os.rename(dst, old)
            os.rename(src, dst)
            try:
                os.unlink(old)
            except Exception:
                pass
else:
    rename = os.rename
    can_rename_open_file = True


class AtomicFile(object):
    """A file that appears atomically with its full content.

    This file-like object writes to a temporary file in the same directory
    as the final file. If the file is committed, the temporary file is renamed
    atomically (on Unix, at least) to its final name. If it is rolled back,
    the temporary file is removed.
    """
    def __init__(self, path, mode='w', bufsize=-1):
        self._file = None
        self._path = os.path.realpath(path)
        dir, name = os.path.split(self._path)
        fd, self._temp = tempfile.mkstemp(prefix=name + '-', dir=dir)
        self._file = os.fdopen(fd, mode, bufsize)

        # Try to preserve permissions and group ownership, but failure
        # should not be fatal
        try:
            st = os.stat(self._path)
            if hasattr(os, 'chmod'):
                os.chmod(self._temp, st.st_mode)
            if hasattr(os, 'chflags') and hasattr(st, 'st_flags'):
                os.chflags(self._temp, st.st_flags)
            if hasattr(os, 'chown'):
                os.chown(self._temp, -1, st.st_gid)
        except OSError:
            pass

    def __getattr__(self, name):
        return getattr(self._file, name)

    def commit(self):
        if self._file is None:
            return
        try:
            f, self._file = self._file, None
            f.close()
            rename(self._temp, self._path)
        except Exception:
            os.unlink(self._temp)
            raise

    def rollback(self):
        if self._file is None:
            return
        try:
            f, self._file = self._file, None
            f.close()
        finally:
            try:
                os.unlink(self._temp)
            except Exception:
                pass

    close = commit
    __del__ = rollback

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    closed = property(lambda self: self._file is None or self._file.closed)


def read_file(path, mode='r'):
    """Read a file and return its content."""
    with open(path, mode) as f:
        return f.read()


def create_file(path, data='', mode='w'):
    """Create a new file with the given data."""
    with open(path, mode) as f:
        if data:
            f.write(data)


def create_unique_file(path):
    """Create a new file. An index is added if the path exists"""
    parts = os.path.splitext(path)
    idx = 1
    while 1:
        try:
            flags = os.O_CREAT + os.O_WRONLY + os.O_EXCL
            if hasattr(os, 'O_BINARY'):
                flags += os.O_BINARY
            return path, os.fdopen(os.open(path, flags, 0666), 'w')
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise
            idx += 1
            # A sanity check
            if idx > 100:
                raise Exception('Failed to create unique name: ' + path)
            path = '%s.%d%s' % (parts[0], idx, parts[1])


if os.name == 'nt':
    def touch_file(filename):
        """Update modified time of the given file. The file is created if
        missing."""
        # Use f.truncate() to avoid low resolution of GetSystemTime()
        # on Windows
        with open(filename, 'ab') as f:
            stat = os.fstat(f.fileno())
            f.truncate(stat.st_size)
else:
    def touch_file(filename):
        """Update modified time of the given file. The file is created if
        missing."""
        try:
            os.utime(filename, None)
        except OSError, e:
            if e.errno == errno.ENOENT:
                with open(filename, 'ab'):
                    pass


def create_zipinfo(filename, mtime=None, dir=False, executable=False, symlink=False,
                   comment=None):
    """Create a instance of `ZipInfo`.

    :param filename: file name of the entry
    :param mtime: modified time of the entry
    :param dir: if `True`, the entry is a directory
    :param executable: if `True`, the entry is a executable file
    :param symlink: if `True`, the entry is a symbolic link
    :param comment: comment of the entry
    """
    from zipfile import ZipInfo, ZIP_DEFLATED, ZIP_STORED
    zipinfo = ZipInfo()

    # The general purpose bit flag 11 is used to denote
    # UTF-8 encoding for path and comment. Only set it for
    # non-ascii files for increased portability.
    # See http://www.pkware.com/documents/casestudies/APPNOTE.TXT
    if any(ord(c) >= 128 for c in filename):
        zipinfo.flag_bits |= 0x0800
    zipinfo.filename = filename.encode('utf-8')

    if mtime is not None:
        mtime = to_datetime(mtime, utc)
        zipinfo.date_time = mtime.utctimetuple()[:6]
        # The "extended-timestamp" extra field is used for the
        # modified time of the entry in unix time. It avoids
        # extracting wrong modified time if non-GMT timezone.
        # See http://www.opensource.apple.com/source/zip/zip-6/unzip/unzip
        #     /proginfo/extra.fld
        zipinfo.extra += struct.pack(
            '<hhBl',
            0x5455,                 # extended-timestamp extra block type
            1 + 4,                  # size of this block
            1,                      # modification time is present
            to_timestamp(mtime))    # time of last modification

    # external_attr is 4 bytes in size. The high order two
    # bytes represent UNIX permission and file type bits,
    # while the low order two contain MS-DOS FAT file
    # attributes, most notably bit 4 marking directories.
    if dir:
        if not zipinfo.filename.endswith('/'):
            zipinfo.filename += '/'
        zipinfo.compress_type = ZIP_STORED
        zipinfo.external_attr = 040755 << 16L        # permissions drwxr-xr-x
        zipinfo.external_attr |= 0x10                # MS-DOS directory flag
    else:
        zipinfo.compress_type = ZIP_DEFLATED
        zipinfo.external_attr = 0644 << 16L          # permissions -r-wr--r--
        if executable:
            zipinfo.external_attr |= 0755 << 16L     # -rwxr-xr-x
        if symlink:
            zipinfo.compress_type = ZIP_STORED
            zipinfo.external_attr |= 0120000 << 16L  # symlink file type

    if comment:
        zipinfo.comment = comment.encode('utf-8')

    return zipinfo


class NaivePopen(object):
    """This is a deadlock-safe version of popen that returns an object with
    errorlevel, out (a string) and err (a string).

    The optional `input`, which must be a `str` object, is first written
    to a temporary file from which the process will read.

    (`capturestderr` may not work under Windows 9x.)

    Example::

      print Popen3('grep spam','\\n\\nhere spam\\n\\n').out
    """
    def __init__(self, command, input=None, capturestderr=None):
        outfile = tempfile.mktemp()
        command = '( %s ) > %s' % (command, outfile)
        if input is not None:
            infile = tempfile.mktemp()
            tmp = open(infile, 'w')
            tmp.write(input)
            tmp.close()
            command = command + ' <' + infile
        if capturestderr:
            errfile = tempfile.mktemp()
            command = command + ' 2>' + errfile
        try:
            self.err = None
            self.errorlevel = os.system(command) >> 8
            self.out = read_file(outfile)
            if capturestderr:
                self.err = read_file(errfile)
        finally:
            if os.path.isfile(outfile):
                os.remove(outfile)
            if input and os.path.isfile(infile):
                os.remove(infile)
            if capturestderr and os.path.isfile(errfile):
                os.remove(errfile)


def terminate(process):
    """Python 2.5 compatibility method.
    os.kill is not available on Windows before Python 2.7.
    In Python 2.6 subprocess.Popen has a terminate method.
    (It also seems to have some issues on Windows though.)
    """

    def terminate_win(process):
        import ctypes
        PROCESS_TERMINATE = 1
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE,
                                                    False,
                                                    process.pid)
        ctypes.windll.kernel32.TerminateProcess(handle, -1)
        ctypes.windll.kernel32.CloseHandle(handle)

    def terminate_nix(process):
        import os
        import signal
        try:
            os.kill(process.pid, signal.SIGTERM)
        except OSError, e:
            # If the process has already finished and has not been
            # waited for, killing it raises an ESRCH error on Cygwin
            if e.errno != errno.ESRCH:
                raise

    if sys.platform == 'win32':
        return terminate_win(process)
    return terminate_nix(process)


def makedirs(path, overwrite=False):
    """Create as many directories as necessary to make `path` exist.

    If `overwrite` is `True`, don't raise an exception in case `path`
    already exists.
    """
    if overwrite and os.path.exists(path):
        return
    os.makedirs(path)


def copytree(src, dst, symlinks=False, skip=[], overwrite=False):
    """Recursively copy a directory tree using copy2() (from shutil.copytree.)

    Added a `skip` parameter consisting of absolute paths
    which we don't want to copy.
    """
    def str_path(path):
        if isinstance(path, unicode):
            path = path.encode(sys.getfilesystemencoding() or
                               getpreferredencoding())
        return path

    def remove_if_overwriting(path):
        if overwrite and os.path.exists(path):
            os.unlink(path)

    skip = [str_path(f) for f in skip]
    def copytree_rec(src, dst):
        names = os.listdir(src)
        makedirs(dst, overwrite=overwrite)
        errors = []
        for name in names:
            srcname = os.path.join(src, name)
            if srcname in skip:
                continue
            dstname = os.path.join(dst, name)
            try:
                if symlinks and os.path.islink(srcname):
                    remove_if_overwriting(dstname)
                    linkto = os.readlink(srcname)
                    os.symlink(linkto, dstname)
                elif os.path.isdir(srcname):
                    copytree_rec(srcname, dstname)
                else:
                    remove_if_overwriting(dstname)
                    shutil.copy2(srcname, dstname)
                # XXX What about devices, sockets etc.?
            except (IOError, OSError), why:
                errors.append((srcname, dstname, str(why)))
            # catch the Error from the recursive copytree so that we can
            # continue with other files
            except shutil.Error, err:
                errors.extend(err.args[0])
        try:
            shutil.copystat(src, dst)
        except WindowsError:
            pass  # Ignore errors due to limited Windows copystat support
        except OSError, why:
            errors.append((src, dst, str(why)))
        if errors:
            raise shutil.Error(errors)
    copytree_rec(str_path(src), str_path(dst))


def is_path_below(path, parent):
    """Return True iff `path` is equal to parent or is located below `parent`
    at any level.
    """
    path = os.path.abspath(path)
    parent = os.path.abspath(parent)
    return path == parent or path.startswith(parent + os.sep)


class file_or_std(object):
    """Context manager for opening a file or using a standard stream

    If `filename` is non-empty, open the file and close it when exiting the
    block. Otherwise, use `sys.stdin` if opening for reading, or `sys.stdout`
    if opening for writing or appending."""

    file = None

    def __init__(self, filename, mode='r', bufsize=-1):
        self.filename = filename
        self.mode = mode
        self.bufsize = bufsize

    def __enter__(self):
        if not self.filename:
            return sys.stdin if 'r' in self.mode else sys.stdout
        self.file = open(self.filename, self.mode, self.bufsize)
        return self.file

    def __exit__(self, et, ev, tb):
        if self.file is not None:
            self.file.close()


# -- sys utils

def fq_class_name(obj):
    """Return the fully qualified class name of given object."""
    c = type(obj)
    m, n = c.__module__, c.__name__
    return n if m == '__builtin__' else '%s.%s' % (m, n)


def arity(f):
    """Return the number of arguments expected by the given function, unbound
    or bound method.
    """
    return f.func_code.co_argcount - bool(getattr(f, 'im_self', False))


def get_last_traceback():
    """Retrieve the last traceback as an `unicode` string."""
    import traceback
    from StringIO import StringIO
    tb = StringIO()
    traceback.print_exc(file=tb)
    return to_unicode(tb.getvalue())


_egg_path_re = re.compile(r'build/bdist\.[^/]+/egg/(.*)')
def get_lines_from_file(filename, lineno, context=0, globals=None):
    """Return `content` number of lines before and after the specified
    `lineno` from the (source code) file identified by `filename`.

    Returns a `(lines_before, line, lines_after)` tuple.
    """
    # The linecache module can load source code from eggs since Python 2.6.
    # Prior versions return lines from the wrong file, so we try locating
    # the file in eggs manually first.
    lines = []
    match = _egg_path_re.match(filename)
    if match:
        import zipfile
        for path in sys.path:
            try:
                zip = zipfile.ZipFile(path, 'r')
                try:
                    lines = zip.read(match.group(1)).splitlines()
                    break
                finally:
                    zip.close()
            except Exception:
                pass

    if not lines:
        import linecache
        linecache.checkcache(filename)
        lines = linecache.getlines(filename, globals)

    if not 0 <= lineno < len(lines):
        return (), None, ()
    lbound = max(0, lineno - context)
    ubound = lineno + 1 + context

    charset = None
    rep = re.compile('coding[=:]\s*([-\w.]+)')
    for linestr in lines[:2]:
        match = rep.search(linestr)
        if match:
            charset = match.group(1)
            break

    before = [to_unicode(l.rstrip('\n'), charset)
              for l in lines[lbound:lineno]]
    line = to_unicode(lines[lineno].rstrip('\n'), charset)
    after = [to_unicode(l.rstrip('\n'), charset)
             for l in lines[lineno + 1:ubound]]

    return before, line, after


def get_frame_info(tb):
    """Return frame information for a traceback."""
    frames = []
    while tb:
        tb_hide = tb.tb_frame.f_locals.get('__traceback_hide__')
        if tb_hide in ('before', 'before_and_this'):
            del frames[:]
            tb_hide = tb_hide[6:]
        if not tb_hide:
            filename = tb.tb_frame.f_code.co_filename
            filename = filename.replace('\\', '/')
            lineno = tb.tb_lineno - 1
            before, line, after = get_lines_from_file(filename, lineno, 5,
                                                      tb.tb_frame.f_globals)
            frames.append({'traceback': tb, 'filename': filename,
                           'lineno': lineno, 'line': line,
                           'lines_before': before, 'lines_after': after,
                           'function': tb.tb_frame.f_code.co_name,
                           'vars': tb.tb_frame.f_locals})
        tb = tb.tb_next
    return frames


def safe__import__(module_name):
    """
    Safe imports: rollback after a failed import.

    Initially inspired from the RollbackImporter in PyUnit,
    but it's now much simpler and works better for our needs.

    See http://pyunit.sourceforge.net/notes/reloading.html
    """
    already_imported = sys.modules.copy()
    try:
        return __import__(module_name, globals(), locals(), [])
    except Exception, e:
        for modname in sys.modules.copy():
            if modname not in already_imported:
                del(sys.modules[modname])
        raise e


def safe_repr(x):
    """`repr` replacement which "never" breaks.

    Make sure we always get a representation of the input `x`
    without risking to trigger an exception (e.g. from a buggy
    `x.__repr__`).

    .. versionadded :: 1.0
    """
    try:
        return to_unicode(repr(x))
    except Exception, e:
        return "<%s object at 0x%X (repr() error: %s)>" % (
            fq_class_name(x), id(x), exception_to_unicode(e))


def get_doc(obj):
    """Return the docstring of an object as a tuple `(summary, description)`,
    where `summary` is the first paragraph and `description` is the remaining
    text.
    """
    doc = inspect.getdoc(obj)
    if not doc:
        return None, None
    doc = to_unicode(doc).split('\n\n', 1)
    summary = doc[0].replace('\n', ' ')
    description = doc[1] if len(doc) > 1 else None
    return summary, description


_dont_import = frozenset(['__file__', '__name__', '__package__'])
def import_namespace(globals_dict, module_name):
    """Import the namespace of a module into a globals dict.

    This function is used in stub modules to import all symbols defined in
    another module into the global namespace of the stub, usually for
    backward compatibility.
    """
    __import__(module_name)
    module = sys.modules[module_name]
    globals_dict.update(item for item in module.__dict__.iteritems()
                        if item[0] not in _dont_import)
    globals_dict.pop('import_namespace', None)


# -- setuptools utils

def get_module_path(module):
    """Return the base path the given module is imported from"""
    path = module.__file__
    module_name = module.__name__
    if path.endswith(('.pyc', '.pyo')):
        path = path[:-1]
    if os.path.basename(path) == '__init__.py':
        path = os.path.dirname(path)
    base_path = os.path.splitext(path)[0]
    while base_path.replace(os.sep, '.').endswith(module_name):
        base_path = os.path.dirname(base_path)
        module_name = '.'.join(module_name.split('.')[:-1])
        if not module_name:
            break
    return base_path


def get_sources(path):
    """Return a dictionary mapping Python module source paths to the
    distributions that contain them.
    """
    sources = {}
    for dist in find_distributions(path, only=True):
        if not dist.has_metadata('top_level.txt'):
            continue
        toplevels = dist.get_metadata_lines('top_level.txt')
        toplevels = [top + '/' for top in toplevels]
        if dist.has_metadata('SOURCES.txt'):  # *.egg-info/SOURCES.txt
            sources.update((src, dist)
                           for src in dist.get_metadata_lines('SOURCES.txt')
                           if any(src.startswith(top) for top in toplevels))
            continue
        if dist.has_metadata('RECORD'):  # *.dist-info/RECORD
            reader = csv.reader(StringIO(dist.get_metadata('RECORD')))
            sources.update((row[0], dist)
                           for row in reader if any(row[0].startswith(top)
                                                    for top in toplevels))
            continue
    return sources


def get_pkginfo(dist):
    """Get a dictionary containing package information for a package

    `dist` can be either a Distribution instance or, as a shortcut,
    directly the module instance, if one can safely infer a Distribution
    instance from it.

    Always returns a dictionary but it will be empty if no Distribution
    instance can be created for the given module.
    """
    import email
    import types
    from trac.util.translation import _

    def parse_pkginfo(dist, name):
        return email.message_from_string(to_utf8(dist.get_metadata(name)))

    if isinstance(dist, types.ModuleType):
        def has_resource(dist, module, resource_name):
            if dist.location.endswith('.egg'):  # installed by easy_install
                return dist.has_resource(resource_name)
            if dist.has_metadata('installed-files.txt'):  # installed by pip
                resource_name = os.path.normpath('../' + resource_name)
                return any(resource_name == os.path.normpath(name)
                           for name
                           in dist.get_metadata_lines('installed-files.txt'))
            if dist.has_metadata('SOURCES.txt'):
                resource_name = os.path.normpath(resource_name)
                return any(resource_name == os.path.normpath(name)
                           for name in dist.get_metadata_lines('SOURCES.txt'))
            if dist.has_metadata('RECORD'):  # *.dist-info/RECORD
                reader = csv.reader(StringIO(dist.get_metadata('RECORD')))
                return any(resource_name == row[0] for row in reader)
            if dist.has_metadata('PKG-INFO'):
                try:
                    pkginfo = parse_pkginfo(dist, 'PKG-INFO')
                    provides = pkginfo.get_all('Provides', ())
                    names = module.__name__.split('.')
                    if any('.'.join(names[:n + 1]) in provides
                           for n in xrange(len(names))):
                        return True
                except (IOError, email.Errors.MessageError):
                    pass
            toplevel = resource_name.split('/')[0]
            if dist.has_metadata('top_level.txt'):
                return toplevel in dist.get_metadata_lines('top_level.txt')
            return dist.key == toplevel.lower()
        module = dist
        module_path = get_module_path(module)
        resource_name = module.__name__.replace('.', '/')
        if os.path.basename(module.__file__) in ('__init__.py', '__init__.pyc',
                                                 '__init__.pyo'):
            resource_name += '/__init__.py'
        else:
            resource_name += '.py'
        for dist in find_distributions(module_path, only=True):
            if os.path.isfile(module_path) or \
                    has_resource(dist, module, resource_name):
                break
        else:
            return {}

    attrs = ('author', 'author-email', 'license', 'home-page', 'summary',
             'description', 'version')
    info = {}
    def normalize(attr):
        return attr.lower().replace('-', '_')
    metadata = 'METADATA' if dist.has_metadata('METADATA') else 'PKG-INFO'
    try:
        pkginfo = parse_pkginfo(dist, metadata)
        for attr in [key for key in attrs if key in pkginfo]:
            info[normalize(attr)] = pkginfo[attr]
    except IOError, e:
        err = _("Failed to read %(metadata)s file for %(dist)s: %(err)s",
                metadata=metadata, dist=dist, err=to_unicode(e))
        for attr in attrs:
            info[normalize(attr)] = err
    except email.Errors.MessageError, e:
        err = _("Failed to parse %(metadata)s file for %(dist)s: %(err)s",
                metadata=metadata, dist=dist, err=to_unicode(e))
        for attr in attrs:
            info[normalize(attr)] = err
    return info


def warn_setuptools_issue(out=None):
    if not out:
        out = sys.stderr
    import setuptools
    from pkg_resources import parse_version as parse
    if parse('5.4') <= parse(setuptools.__version__) < parse('5.7') and \
            not os.environ.get('PKG_RESOURCES_CACHE_ZIP_MANIFESTS'):
        out.write("Warning: Detected setuptools version %s. The environment "
                  "variable 'PKG_RESOURCES_CACHE_ZIP_MANIFESTS' must be set "
                  "to avoid significant performance degradation.\n"
                  % setuptools.__version__)


# -- crypto utils

try:
    os.urandom(16)
    urandom = os.urandom

except NotImplementedError:
    _entropy = random.Random()

    def urandom(n):
        result = []
        hasher = sha1(str(os.getpid()) + str(time_now()))
        while len(result) * hasher.digest_size < n:
            hasher.update(str(_entropy.random()))
            result.append(hasher.digest())
        result = ''.join(result)
        return result[:n] if len(result) > n else result


def hex_entropy(digits=32):
    """Generate `digits` number of hex digits of entropy."""
    result = ''.join('%.2x' % ord(v) for v in urandom((digits + 1) // 2))
    return result[:digits] if len(result) > digits else result


# Original license for md5crypt:
# Based on FreeBSD src/lib/libcrypt/crypt.c 1.2
#
# "THE BEER-WARE LICENSE" (Revision 42):
# <phk@login.dknet.dk> wrote this file.  As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a beer in return.   Poul-Henning Kamp
def md5crypt(password, salt, magic='$1$'):
    """Based on FreeBSD src/lib/libcrypt/crypt.c 1.2

    :param password: the plain text password to crypt
    :param salt: the raw salt
    :param magic: our magic string
    """
    # /* The password first, since that is what is most unknown */
    # /* Then our magic string */
    # /* Then the raw salt */
    m = md5(password + magic + salt)

    # /* Then just as many characters of the MD5(pw,salt,pw) */
    mixin = md5(password + salt + password).digest()
    for i in range(0, len(password)):
        m.update(mixin[i % 16])

    # /* Then something really weird... */
    # Also really broken, as far as I can tell.  -m
    i = len(password)
    while i:
        if i & 1:
            m.update('\x00')
        else:
            m.update(password[0])
        i >>= 1

    final = m.digest()

    # /* and now, just to make sure things don't run too fast */
    for i in range(1000):
        m2 = md5()
        if i & 1:
            m2.update(password)
        else:
            m2.update(final)

        if i % 3:
            m2.update(salt)

        if i % 7:
            m2.update(password)

        if i & 1:
            m2.update(final)
        else:
            m2.update(password)

        final = m2.digest()

    # This is the bit that uses to64() in the original code.

    itoa64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

    rearranged = ''
    for a, b, c in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5)):
        v = ord(final[a]) << 16 | ord(final[b]) << 8 | ord(final[c])
        for i in range(4):
            rearranged += itoa64[v & 0x3f]
            v >>= 6

    v = ord(final[11])
    for i in range(2):
        rearranged += itoa64[v & 0x3f]
        v >>= 6

    return magic + salt + '$' + rearranged


# -- data structures

class Ranges(object):
    """Holds information about ranges parsed from a string

    :author: Tim Hatch

    >>> x = Ranges("1,2,9-15")
    >>> 1 in x
    True
    >>> 5 in x
    False
    >>> 10 in x
    True
    >>> 16 in x
    False
    >>> [i for i in range(20) if i in x]
    [1, 2, 9, 10, 11, 12, 13, 14, 15]

    Also supports iteration, which makes that last example a bit simpler:

    >>> list(x)
    [1, 2, 9, 10, 11, 12, 13, 14, 15]

    Note that it automatically reduces the list and short-circuits when the
    desired ranges are a relatively small portion of the entire set:

    >>> x = Ranges("99")
    >>> 1 in x # really fast
    False
    >>> x = Ranges("1, 2, 1-2, 2") # reduces this to 1-2
    >>> x.pairs
    [(1, 2)]
    >>> x = Ranges("1-9,2-4") # handle ranges that completely overlap
    >>> list(x)
    [1, 2, 3, 4, 5, 6, 7, 8, 9]

    The members 'a' and 'b' refer to the min and max value of the range, and
    are None if the range is empty:

    >>> x.a
    1
    >>> x.b
    9
    >>> e = Ranges()
    >>> e.a, e.b
    (None, None)

    Empty ranges are ok, and ranges can be constructed in pieces, if you
    so choose:

    >>> x = Ranges()
    >>> x.appendrange("1, 2, 3")
    >>> x.appendrange("5-9")
    >>> x.appendrange("2-3") # reduce'd away
    >>> list(x)
    [1, 2, 3, 5, 6, 7, 8, 9]

    Reversed ranges are ignored, unless the Ranges has the `reorder` property
    set.

    >>> str(Ranges("20-10"))
    ''
    >>> str(Ranges("20-10", reorder=True))
    '10-20'

    As rendered ranges are often using u',\u200b' (comma + Zero-width
    space) to enable wrapping, we also support reading such ranges, as
    they can be copy/pasted back.

    >>> str(Ranges(u'1,\u200b3,\u200b5,\u200b6,\u200b7,\u200b9'))
    '1,3,5-7,9'

    """

    RE_STR = ur'[0-9]+(?:[-:][0-9]+)?(?:,\u200b?[0-9]+(?:[-:][0-9]+)?)*'

    def __init__(self, r=None, reorder=False):
        self.pairs = []
        self.a = self.b = None
        self.reorder = reorder
        self.appendrange(r)

    def appendrange(self, r):
        """Add ranges to the current one.

        A range is specified as a string of the form "low-high", and
        `r` can be a list of such strings, a string containing comma-separated
        ranges, or `None`.
        """
        if not r:
            return
        p = self.pairs
        if isinstance(r, basestring):
            r = re.split(u',\u200b?', r)
        for x in r:
            try:
                a, b = map(int, x.split('-', 1))
            except ValueError:
                a, b = int(x), int(x)
            if b >= a:
                p.append((a, b))
            elif self.reorder:
                p.append((b, a))
        self._reduce()

    def _reduce(self):
        """Come up with the minimal representation of the ranges"""
        p = self.pairs
        p.sort()
        i = 0
        while i + 1 < len(p):
            if p[i+1][0]-1 <= p[i][1]:  # this item overlaps with the next
                # make the first include the second
                p[i] = (p[i][0], max(p[i][1], p[i+1][1]))
                del p[i+1]  # delete the second, after adjusting my endpoint
            else:
                i += 1
        if p:
            self.a = p[0][0]   # min value
            self.b = p[-1][1]  # max value
        else:
            self.a = self.b = None

    def __iter__(self):
        """
        This is another way I came up with to do it.  Is it faster?

        from itertools import chain
        return chain(*[xrange(a, b+1) for a, b in self.pairs])
        """
        for a, b in self.pairs:
            for i in range(a, b+1):
                yield i

    def __contains__(self, x):
        """
        >>> 55 in Ranges()
        False
        """
        # short-circuit if outside the possible range
        if self.a is not None and self.a <= x <= self.b:
            for a, b in self.pairs:
                if a <= x <= b:
                    return True
                if b > x: # short-circuit if we've gone too far
                    break
        return False

    def __str__(self):
        """Provide a compact string representation of the range.

        >>> (str(Ranges("1,2,3,5")), str(Ranges()), str(Ranges('2')))
        ('1-3,5', '', '2')
        >>> str(Ranges('99-1')) # only nondecreasing ranges allowed
        ''
        """
        r = []
        for a, b in self.pairs:
            if a == b:
                r.append(str(a))
            else:
                r.append("%d-%d" % (a, b))
        return ",".join(r)

    def __len__(self):
        """The length of the entire span, ignoring holes.

        >>> (len(Ranges('99')), len(Ranges('1-2')), len(Ranges('')))
        (1, 2, 0)
        """
        if self.a is None or self.b is None:
            return 0
        # Result must fit an int
        return min(self.b - self.a + 1, sys.maxint)

    def __nonzero__(self):
        """Return True iff the range is not empty.

        >>> (bool(Ranges()), bool(Ranges('1-2')))
        (False, True)
        """
        return self.a is not None and self.b is not None

    def truncate(self, max):
        """Truncate the Ranges by setting a maximal allowed value.

        Note that this `max` can be a value in a gap, so the only guarantee
        is that `self.b` will be lesser than or equal to `max`.

        >>> r = Ranges("10-20,25-45")
        >>> str(r.truncate(30))
        '10-20,25-30'

        >>> str(r.truncate(22))
        '10-20'

        >>> str(r.truncate(10))
        '10'
        """
        r = Ranges()
        r.a, r.b, r.reorder = self.a, self.b, self.reorder
        r.pairs = []
        for a, b in self.pairs:
            if a <= max:
                if b > max:
                    r.pairs.append((a, max))
                    r.b = max
                    break
                r.pairs.append((a, b))
            else:
                break
        return r


def to_ranges(revs):
    """Converts a list of revisions to a minimal set of ranges.

    >>> to_ranges([2, 12, 3, 6, 9, 1, 5, 11])
    '1-3,5-6,9,11-12'
    >>> to_ranges([])
    ''
    """
    ranges = []
    begin = end = None
    def store():
        if end == begin:
            ranges.append(str(begin))
        else:
            ranges.append('%d-%d' % (begin, end))
    for rev in sorted(revs):
        if begin is None:
            begin = end = rev
        elif rev == end + 1:
            end = rev
        else:
            store()
            begin = end = rev
    if begin is not None:
        store()
    return ','.join(ranges)


class lazy(object):
    """A lazily-evaluated attribute.

    :since: 1.0
    """

    def __init__(self, fn):
        self.fn = fn
        functools.update_wrapper(self, fn)

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if self.fn.__name__ in instance.__dict__:
            return instance.__dict__[self.fn.__name__]
        result = self.fn(instance)
        instance.__dict__[self.fn.__name__] = result
        return result

    def __set__(self, instance, value):
        instance.__dict__[self.fn.__name__] = value

    def __delete__(self, instance):
        del instance.__dict__[self.fn.__name__]


# -- algorithmic utilities

DIGITS = re.compile(r'(\d+)')
def embedded_numbers(s):
    """Comparison function for natural order sorting based on
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/214202."""
    pieces = DIGITS.split(s)
    pieces[1::2] = map(int, pieces[1::2])
    return pieces


def pairwise(iterable):
    """
    >>> list(pairwise([0, 1, 2, 3]))
    [(0, 1), (1, 2), (2, 3)]

    .. deprecated :: 0.11
       if this really needs to be used, rewrite it without izip
    """
    a, b = tee(iterable)
    try:
        b.next()
    except StopIteration:
        pass
    return izip(a, b)


def partition(iterable, order=None):
    """
    >>> partition([(1, "a"), (2, "b"), (3, "a")])
    {'a': [1, 3], 'b': [2]}
    >>> partition([(1, "a"), (2, "b"), (3, "a")], "ab")
    [[1, 3], [2]]
    """
    result = {}
    if order is not None:
        for key in order:
            result[key] = []
    for item, category in iterable:
        result.setdefault(category, []).append(item)
    if order is None:
        return result
    return [result[key] for key in order]


def as_int(s, default, min=None, max=None):
    """Convert s to an int and limit it to the given range, or return default
    if unsuccessful."""
    try:
        value = int(s)
    except (TypeError, ValueError):
        return default
    if min is not None and value < min:
        value = min
    if max is not None and value > max:
        value = max
    return value


def as_bool(value):
    """Convert the given value to a `bool`.

    If `value` is a string, return `True` for any of "yes", "true", "enabled",
    "on" or non-zero numbers, ignoring case. For non-string arguments, return
    the argument converted to a `bool`, or `False` if the conversion fails.
    """
    if isinstance(value, basestring):
        try:
            return bool(float(value))
        except ValueError:
            return value.strip().lower() in ('yes', 'true', 'enabled', 'on')
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def pathjoin(*args):
    """Strip `/` from the arguments and join them with a single `/`."""
    return '/'.join(filter(None, (each.strip('/') for each in args if each)))


def to_list(splittable, sep=','):
    """Split a string at `sep` and return a list without any empty items.
    """
    split = [x.strip() for x in splittable.split(sep)]
    return [item for item in split if item]


# Imports for backward compatibility (at bottom to avoid circular dependencies)
from trac.core import TracError
from trac.util.compat import reversed
from trac.util.html import escape, unescape, Markup, Deuglifier
from trac.util.text import CRLF, to_utf8, shorten_line, wrap, pretty_size
from trac.util.datefmt import pretty_timedelta, format_datetime, \
                              format_date, format_time, \
                              get_date_format_hint, \
                              get_datetime_format_hint, http_date, \
                              parse_date

__no_apidoc__ = 'compat presentation translation'
