# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2006 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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

import errno
import inspect
from itertools import izip, tee
import locale
import os.path
from pkg_resources import find_distributions
import random
import re
import shutil
import sys
import tempfile
import time
from urllib import quote, unquote, urlencode

from trac.util.compat import any, md5, sha1, sorted
from trac.util.text import to_unicode

# -- req/session utils

def get_reporter_id(req, arg_name=None):
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

if os.name == 'nt':
    from getpass import getuser
else:
    import pwd
    def getuser():
        try:
            return pwd.getpwuid(os.geteuid())[0]
        except KeyError:
            return 'unknown'

# -- algorithmic utilities

DIGITS = re.compile(r'(\d+)')
def embedded_numbers(s):
    """Comparison function for natural order sorting based on
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/214202."""
    pieces = DIGITS.split(s)
    pieces[1::2] = map(int, pieces[1::2])
    return pieces


# -- os utilities

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
        self._path = path
        (dir, name) = os.path.split(path)
        (fd, self._temp) = tempfile.mkstemp(prefix=name + '-', dir=dir)
        self._file = os.fdopen(fd, mode, bufsize)
        
        # Try to preserve permissions and group ownership, but failure
        # should not be fatal
        try:
            st = os.stat(path)
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
            except:
                pass
    
    close = commit
    __del__ = rollback


def read_file(path, mode='r'):
    """Read a file and return its content."""
    f = open(path, mode)
    try:
        return f.read()
    finally:
        f.close()


def create_file(path, data='', mode='w'):
    """Create a new file with the given data."""
    f = open(path, mode)
    try:
        if data:
            f.write(data)
    finally:
        f.close()


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


class NaivePopen:
    """This is a deadlock-safe version of popen that returns an object with
    errorlevel, out (a string) and err (a string).

    The optional `input`, which must be a `str` object, is first written
    to a temporary file from which the process will read.
    
    (`capturestderr` may not work under Windows 9x.)

    Example: print Popen3('grep spam','\n\nhere spam\n\n').out
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
            outfd = file(outfile, 'r')
            self.out = outfd.read()
            outfd.close()
            if capturestderr:
                errfd = file(errfile,'r')
                self.err = errfd.read()
                errfd.close()
        finally:
            if os.path.isfile(outfile):
                os.remove(outfile)
            if input and os.path.isfile(infile):
                os.remove(infile)
            if capturestderr and os.path.isfile(errfile):
                os.remove(errfile)


def makedirs(path, overwrite=False):
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
                               locale.getpreferredencoding())
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
        except WindowsError, why:
            pass # Ignore errors due to limited Windows copystat support
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


# -- sys utils

def arity(f):
    """Return the number of arguments expected by the given function, unbound
    or bound method.
    """
    return f.func_code.co_argcount - bool(getattr(f, 'im_self', False))


def get_last_traceback():
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
        if arity(linecache.getlines) >= 2:
            lines = linecache.getlines(filename, globals)
        else:   # Python 2.4
            lines = linecache.getlines(filename)

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
    after = [to_unicode(l.rstrip('\n'), charset) \
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
            if not already_imported.has_key(modname):
                del(sys.modules[modname])
        raise e


def get_doc(obj):
    """Return the docstring of an object as a tuple `(summary, description)`,
    where `summary` is the first paragraph and `description` is the remaining
    text.
    """
    doc = inspect.getdoc(obj)
    if not doc:
        return (None, None)
    doc = to_unicode(doc).split('\n\n', 1)
    summary = doc[0].replace('\n', ' ')
    description = len(doc) > 1 and doc[1] or None
    return (summary, description)

# -- setuptools utils

def get_module_path(module):
    """Return the base path the given module is imported from"""
    path = module.__file__
    module_name = module.__name__
    if path.endswith('.pyc') or path.endswith('.pyo'):
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
        try:
            toplevels = dist.get_metadata('top_level.txt').splitlines()
            toplevels = [each + '/' for each in toplevels]
            files = dist.get_metadata('SOURCES.txt').splitlines()
            sources.update((src, dist) for src in files
                           if any(src.startswith(toplevel)
                                  for toplevel in toplevels))
        except (KeyError, IOError):
            pass    # Metadata not found
    return sources

def get_pkginfo(dist):
    """Get a dictionary containing package information for a package

    `dist` can be either a Distribution instance or, as a shortcut,
    directly the module instance, if one can safely infer a Distribution
    instance from it.
    
    Always returns a dictionary but it will be empty if no Distribution
    instance can be created for the given module.
    """
    import types
    if isinstance(dist, types.ModuleType):
        module = dist
        module_path = get_module_path(module)
        for dist in find_distributions(module_path, only=True):
            if os.path.isfile(module_path) or \
                   dist.key == module.__name__.lower():
                break
        else:
            return {}
    import email
    attrs = ('author', 'author-email', 'license', 'home-page', 'summary',
             'description', 'version')
    info = {}
    def normalize(attr):
        return attr.lower().replace('-', '_')
    try:
        pkginfo = email.message_from_string(dist.get_metadata('PKG-INFO'))
        for attr in [key for key in attrs if key in pkginfo]:
            info[normalize(attr)] = pkginfo[attr]
    except IOError, e:
        err = 'Failed to read PKG-INFO file for %s: %s' % (dist, e)
        for attr in attrs:
            info[normalize(attr)] = err
    except email.Errors.MessageError, e:
        err = 'Failed to parse PKG-INFO file for %s: %s' % (dist, e)
        for attr in attrs:
            info[normalize(attr)] = err
    return info

# -- crypto utils

try:
    os.urandom(16)
    urandom = os.urandom

except NotImplementedError:
    _entropy = random.Random()
    
    def urandom(n):
        result = []
        hasher = sha1(str(os.getpid()) + str(time.time()))
        while len(result) * hasher.digest_size < n:
            hasher.update(str(_entropy.random()))
            result.append(hasher.digest())
        result = ''.join(result)
        return len(result) > n and result[:n] or result


def hex_entropy(bytes=32):
    result = ''.join('%.2x' % ord(v) for v in urandom((bytes + 1) // 2))
    return len(result) > bytes and result[:bytes] or result

# Original license for md5crypt:
# Based on FreeBSD src/lib/libcrypt/crypt.c 1.2
#
# "THE BEER-WARE LICENSE" (Revision 42):
# <phk@login.dknet.dk> wrote this file.  As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a beer in return.   Poul-Henning Kamp
def md5crypt(password, salt, magic='$1$'):
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


# -- misc. utils

class Ranges(object):
    """
    Holds information about ranges parsed from a string
    
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

    ''Code contributed by Tim Hatch''

    Reversed ranges are ignored, unless the Ranges has the `reorder` property 
    set.

    >>> str(Ranges("20-10"))
    ''
    >>> str(Ranges("20-10", reorder=True))
    '10-20'

    """

    RE_STR = r"""\d+(?:[-:]\d+)?(?:,\d+(?:[-:]\d+)?)*"""
    
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
            r = r.split(',')
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
            if p[i+1][0]-1 <= p[i][1]: # this item overlaps with the next
                # make the first include the second
                p[i] = (p[i][0], max(p[i][1], p[i+1][1])) 
                del p[i+1] # delete the second, after adjusting my endpoint
            else:
                i += 1
        if p:
            self.a = p[0][0] # min value
            self.b = p[-1][1] # max value
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
        return min(self.b - self.a + 1, (1 << 31) - 1)

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

def pairwise(iterable):
    """
    >>> list(pairwise([0, 1, 2, 3]))
    [(0, 1), (1, 2), (2, 3)]

    :deprecated: since 0.11 (if this really needs to be used, rewrite it
                             without izip)
    """
    a, b = tee(iterable)
    try:
        b.next()
    except StopIteration:
        pass
    return izip(a, b)

def partition(iterable, order=None):
    """
    >>> partition([(1,"a"),(2, "b"),(3, "a")])
    {'a': [1, 3], 'b': [2]}
    >>> partition([(1,"a"),(2, "b"),(3, "a")], "ab")
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

