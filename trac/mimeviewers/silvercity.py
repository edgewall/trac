# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Daniel Lundin <daniel@edgewall.com>
#
# Syntax highlighting module, based on the SilverCity module.
# Get it at: http://silvercity.sourceforge.net/
# 

import StringIO

supported_types = [               
    (1, 'application/x-httpd-php'),
    (1, 'application/x-httpd-php4'),
    (1, 'application/x-httpd-php3'),
    (7, 'application/x-javascript'),
    (7, 'image/svg+xml'),
    (1, 'text/css'),
    (1, 'text/html'),
    (1, 'text/x-asp'),
    (1, 'text/x-c++src'),
    (1, 'text/x-c++hdr'),
    (1, 'text/x-chdr'),
    (1, 'text/x-csrc'),
    (1, 'text/x-perl'),
    (1, 'text/x-php'),
    (1, 'text/x-psp'),
    (1, 'text/x-python'),
    (1, 'text/x-ruby'),
    (1, 'text/x-sql'),
    (1, 'text/xml'),
    (1, 'text/xslt'),
    (1, 'application/x-test'),
    ]

type_lang = { 'text/css':['CSS'],
              'text/html':['HyperText', {'asp.default.language':1}],
              'application/x-javascript':['CPP'], # Kludgy.
              'text/x-asp':['HyperText', {'asp.default.language':2}],
              'text/x-c++hdr':['CPP'],
              'text/x-c++src':['CPP'],
              'text/x-chdr':['CPP'],
              'text/x-csrc':['CPP'],
              'text/x-perl':['Perl'],
              'text/x-php':['HyperText', {'asp.default.language':4}],
              'application/x-httpd-php':['HyperText', {'asp.default.language':4}],
              'application/x-httpd-php4':['HyperText', {'asp.default.language':4}],
              'application/x-httpd-php3':['HyperText', {'asp.default.language':4}],
              'text/x-psp':['HyperText', {'asp.default.language':3}],
              'text/x-python':['Python'],
              'text/x-ruby':['Ruby'],
              'text/x-sql':['SQL'],
              'text/xml':['XML'],
              'text/xslt':['XSLT'],
              'image/svg+xml':['XML'],
              }

def display(data, mimetype, filename, env):
    import SilverCity
    from SilverCity import LanguageInfo
    try:
        typelang = type_lang[mimetype]
        lang = typelang[0]
        module = getattr(SilverCity, lang)
        generator = getattr(module, lang+"HTMLGenerator")
        try:
            allprops = typelang[1]
            propset = SilverCity.PropertySet()
            for p in allprops.keys():            
                propset[p] = allprops[p]
        except IndexError:
            pass
    except (KeyError, AttributeError):
        err = "No SilverCity lexer found for mime-type '%s'." % mimetype
        raise Exception, err
    io = StringIO.StringIO(data)
    generator().generate_html(io, data)
    html = '<div class="code-block">%s</div>\n' % io.getvalue()
    return html

    
