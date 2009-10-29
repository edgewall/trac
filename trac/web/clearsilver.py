# -*- coding: utf-8 -*-
#
# Copyright (C)2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

from HTMLParser import HTMLParser

from trac.core import TracError
from trac.util.html import Markup, Fragment, escape
from trac.util.text import to_unicode


class HDFWrapper:
    """
    Convenience layer on top of the low-level ClearSilver python bindings
    for HDF manipulation. This class makes the HDF look and behave more
    like a standard Python dict.

    >>> hdf = HDFWrapper()
    >>> hdf['trac.url'] = 'http://trac.edgewall.org/'
    >>> hdf['trac.version'] = '1.0'
    >>> print hdf
    trac {
      url = http://trac.edgewall.org/
      version = 1.0
    }

    HDFWrapper can also assign Python lists and dicts to HDF nodes,
    automatically expanding them into the corresponding HDF structure.

    A dictionary is mapped to a HDF node with named children:

    >>> hdf = HDFWrapper()
    >>> hdf['item'] = {'name': 'An item', 'value': '0'}
    >>> print hdf
    item {
      name = An item
      value = 0
    }

    A sequence is mapped to a HDF node with children whose names are
    the indexes of the elements:

    >>> hdf = HDFWrapper()
    >>> hdf['items'] = ['Item 1', 'Item 2']
    >>> print hdf
    items {
      0 = Item 1
      1 = Item 2
    }

    Simple values can also be easily retrieved using the same syntax.

    >>> hdf = HDFWrapper()
    >>> hdf['time'] = 42
    >>> hdf['time']
    u'42'
    >>> hdf['name'] = 'Foo'
    >>> hdf['name']
    u'Foo'

    An attempt to retrieve a value that hasn't been set will raise a KeyError,
    just like a standard dictionary:

    >>> hdf['undef']
    Traceback (most recent call last):
        ...
    KeyError: 'undef'
    
    It may be preferable to return a default value if the given key does not exit.
    It will return 'None' when the specified key is not present:

    >>> hdf.get('time')
    u'42'
    >>> hdf.get('undef')

    A second argument may be passed to specify the default return value:

    >>> hdf.get('time', 'Undefined Key')
    u'42'
    >>> hdf.get('undef', 'Undefined Key')
    'Undefined Key'

    The 'in' and 'not in' operators can be used to test whether the HDF contains
    a value with a given name.

    >>> 'name' in hdf
    True
    >>> 'undef' in hdf
    False

    has_key() performs the same function:

    >>> hdf.has_key('name')
    True
    >>> hdf.has_key('undef')
    False
    """

    has_clearsilver = None
    
    def __init__(self, loadpaths=[]):
        """Create a new HDF dataset.
        
        The loadpaths parameter can be used to specify a sequence of paths under
        which ClearSilver will search for template files:

        >>> hdf = HDFWrapper(loadpaths=['/etc/templates',
        ...                             '/home/john/templates'])
        >>> print hdf
        hdf {
          loadpaths {
            0 = /etc/templates
            1 = /home/john/templates
          }
        }
        """
        try:
            import neo_cgi
            # The following line is needed so that ClearSilver can be loaded when
            # we are being run in multiple interpreters under mod_python
            neo_cgi.update()
            import neo_util
            self.hdf = neo_util.HDF()
            self.has_clearsilver = True
        except ImportError:
            self.has_clearsilver = False
        
        self['hdf.loadpaths'] = loadpaths

    def __repr__(self):
        return '<HDFWrapper 0x%x>' % id(self)

    def __nonzero__(self):
        return self.has_clearsilver

    def __getattr__(self, name):
        # For backwards compatibility, expose the interface of the underlying HDF
        # object
        if self.has_clearsilver:
            return getattr(self.hdf, name)
        else:
            return None

    def __contains__(self, name):
        return self.hdf.getObj(str(name)) != None
    has_key = __contains__

    def get(self, name, default=None):
        value = self.hdf.getValue(str(name), '<<NONE>>')
        if value == '<<NONE>>':
            return default
        return value.decode('utf-8')

    def __getitem__(self, name):
        value = self.get(name, None)
        if value == None:
            raise KeyError, name
        return value

    def __setitem__(self, name, value):
        """Add data to the HDF dataset.
        
        The `name` parameter is the path of the node in dotted syntax. The
        `value` parameter can be a simple value such as a string or number, but
        also data structures such as dicts and lists.

        >>> hdf = HDFWrapper()

        Adding a simple value results in that value being inserted into the HDF
        after being converted to a string.

        >>> hdf['test.num'] = 42
        >>> hdf['test.num']
        u'42'
        >>> hdf['test.str'] = 'foo'
        >>> hdf['test.str']
        u'foo'

        The boolean literals `True` and `False` are converted to there integer
        representation before being added:

        >>> hdf['test.true'] = True
        >>> hdf['test.true']
        u'1'
        >>> hdf['test.false'] = False
        >>> hdf['test.false']
        u'0'

        If value is `None`, nothing is added to the HDF:

        >>> hdf['test.true'] = None
        >>> hdf['test.none']
        Traceback (most recent call last):
            ...
        KeyError: 'test.none'
        """
        self.set_value(name, value, True)
        
    def set_unescaped(self, name, value):
        """
        Add data to the HDF dataset.
        
        This method works the same way as `__setitem__` except that `value`
        is not escaped if it is a string.
        """
        self.set_value(name, value, False)
        
    def set_value(self, name, value, do_escape=True):
        """
        Add data to the HDF dataset.
        """
        if not self.has_clearsilver:
            return
        def set_unicode(prefix, value):
            self.hdf.setValue(prefix.encode('utf-8'), value.encode('utf-8'))
        def set_str(prefix, value):
            self.hdf.setValue(prefix.encode('utf-8'), str(value))
            
        def add_value(prefix, value):
            if value is None:
                return
            if value in (True, False):
                set_str(prefix, int(value))
            elif isinstance(value, (Markup, Fragment)):
                set_unicode(prefix, unicode(value))
            elif isinstance(value, str):
                if do_escape:
                    # Assume UTF-8 here, for backward compatibility reasons
                    set_unicode(prefix, escape(to_unicode(value)))
                else:
                    set_str(prefix, value)
            elif isinstance(value, unicode):
                if do_escape:
                    set_unicode(prefix, escape(value))
                else:
                    set_unicode(prefix, value)
            elif isinstance(value, dict):
                for k in value.keys():
                    add_value('%s.%s' % (prefix, to_unicode(k)), value[k])
            else:
                if hasattr(value, '__iter__') or \
                        isinstance(value, (list, tuple)):
                    for idx, item in enumerate(value):
                        add_value('%s.%d' % (prefix, idx), item)
                else:
                    set_str(prefix, value)
        add_value(name, value)

    def __str__(self):
        from StringIO import StringIO
        buf = StringIO()
        def hdf_tree_walk(node, prefix=''):
            while node:
                name = node.name() or ''
                buf.write('%s%s' % (prefix, name))
                value = node.value()
                if value or not node.child():
                    if value.find('\n') == -1:
                        buf.write(' = %s' % value)
                    else:
                        buf.write(' = << EOM\n%s\nEOM' % value)
                if node.child():
                    buf.write(' {\n')
                    hdf_tree_walk(node.child(), prefix + '  ')
                    buf.write('%s}\n' % prefix)
                else:
                    buf.write('\n')
                node = node.next()
        hdf_tree_walk(self.hdf.child())
        return buf.getvalue().strip()

    def parse(self, string):
        """Parse the given string as template text, and returns a neo_cs.CS
        object.
        """
        import neo_cs
        cs = neo_cs.CS(self.hdf)
        cs.parseStr(string)
        return cs

    def render(self, template, form_token=None):
        """Render the HDF using the given template.

        The template parameter can be either an already parse neo_cs.CS
        object, or a string. In the latter case it is interpreted as name of the
        template file.
        """
        if isinstance(template, basestring):
            filename = template
            try:
                import neo_cs
            except ImportError:
                raise TracError("You're using a plugin which requires "
                                "the Clearsilver template engine and "
                                "Clearsilver is not installed. "
                                "Either disable that plugin or install "
                                "Clearsilver.")
            template = neo_cs.CS(self.hdf)
            template.parseFile(filename)

        if form_token:
            from cStringIO import StringIO
            out = StringIO()
            injector = FormTokenInjector(form_token, out)
            injector.feed(template.render())
            return out.getvalue()
        else:
            return template.render()


class FormTokenInjector(HTMLParser):
    """Identify and protect forms from CSRF attacks

    This filter works by adding a input type=hidden field to POST forms.
    """
    def __init__(self, form_token, out):
        HTMLParser.__init__(self)
        self.out = out
        self.token = form_token

    def handle_starttag(self, tag, attrs):
        self.out.write(self.get_starttag_text())
        if tag.lower() == 'form':
            for name, value in attrs:
                if name.lower() == 'method' and value.lower() == 'post':
                    self.out.write('<input type="hidden" name="__FORM_TOKEN"'
                                   ' value="%s"/>' % self.token)
                    break
                    
    def handle_startendtag(self, tag, attrs):
        self.out.write(self.get_starttag_text())
        
    def handle_charref(self, name):
        self.out.write('&#%s;' % name)

    def handle_entityref(self, name):
        self.out.write('&%s;' % name)

    def handle_comment(self, data):
        self.out.write('<!--%s-->' % data)

    def handle_decl(self, data):
        self.out.write('<!%s>' % data)

    def handle_pi(self, data):
        self.out.write('<?%s?>' % data)

    def handle_data(self, data):
        self.out.write(data)

    def handle_endtag(self, tag):
        self.out.write('</' + tag + '>')


if __name__ == '__main__':
    import doctest, sys
    doctest.testmod(sys.modules[__name__])
