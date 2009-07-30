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
import locale
import os
import re
import sys
import time
import tempfile
from urllib import quote, unquote, urlencode
from itertools import izip

# Imports for backward compatibility
from trac.core import TracError
from trac.util.compat import md5, reversed, sha1, sorted, tee
from trac.util.html import escape, unescape, Markup, Deuglifier
from trac.util.text import CRLF, to_utf8, to_unicode, shorten_line, \
                           wrap, pretty_size
from trac.util.datefmt import pretty_timedelta, format_datetime, \
                              format_date, format_time, \
                              get_date_format_hint, \
                              get_datetime_format_hint, http_date, \
                              parse_date

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
        if input:
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

# -- sys utils

def arity(f):
    return f.func_code.co_argcount

def get_last_traceback():
    import traceback
    from StringIO import StringIO
    tb = StringIO()
    traceback.print_exc(file=tb)
    return to_unicode(tb.getvalue())

def get_lines_from_file(filename, lineno, context=0):
    """Return `content` number of lines before and after the specified
    `lineno` from the file identified by `filename`.
    
    Returns a `(lines_before, line, lines_after)` tuple.
    """
    if os.path.isfile(filename):
        fileobj = open(filename, 'U')
        try:
            lines = fileobj.readlines()
            lbound = max(0, lineno - context)
            ubound = lineno + 1 + context


            charset = None
            rep = re.compile('coding[=:]\s*([-\w.]+)')
            for linestr in lines[0], lines[1]:
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
        finally:
            fileobj.close()
    return (), None, ()

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

# -- setuptools utils

def get_module_path(module):
    # Determine the plugin that this component belongs to
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
        try:
            from pkg_resources import find_distributions
            module = dist
            module_path = get_module_path(module)
            for dist in find_distributions(module_path, only=True):
                if os.path.isfile(module_path) or \
                       dist.key == module.__name__.lower():
                    break
            else:
                return {}
        except ImportError:
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

def hex_entropy(bytes=32):
    import random
    return sha1(str(random.random())).hexdigest()[:bytes]


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
            rearranged += itoa64[v & 0x3f]; v >>= 6

    v = ord(final[11])
    for i in range(2):
        rearranged += itoa64[v & 0x3f]; v >>= 6

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
        """Add a range (from a string or None) to the current one"""
        if not r:
            return
        p = self.pairs
        for x in r.split(","):
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
        if self.a is not None and self.b is not None:
            return self.b - self.a + 1
        else:
            return 0

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

def content_disposition(type, filename=None):
    """Generate a properly escaped Content-Disposition header"""
    if filename is not None:
        if isinstance(filename, unicode):
            filename = filename.encode('utf-8')
        type += '; filename=' + quote(filename, safe='')
    return type

def pairwise(iterable):
    """s -> (s0,s1), (s1,s2), (s2, s3), ...

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
    result = {}
    if order is not None:
        for key in order:
            result[key] = []
    for item, category in iterable:
        result.setdefault(category, []).append(item)
    if order is None:
        return result
    return [result[key] for key in order]
