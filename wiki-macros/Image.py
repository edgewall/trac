# Adapted from the Image.py macro created by Shun-ichi Goto <gotoh@taiyo.co.jp> 
"""
Display image in attachment or repository into the wiki page.

First argument is filename (file spec).

The file specification may refer attachments:
 * 'module:id:file', with module being either 'wiki' or 'ticket',
   to refer to the attachment named 'file' in the module:id object
 * 'id:file' same as above, module defaulted to 'wiki' (id can be dir/dir/node)
 * 'file' to refer to a local attachment named 'file'
   (but then, this works only from within a wiki page or a ticket).

Also, the file specification may refer to repository files,
using the 'source:file' syntax (or the usual aliases for 'source').


Rest of optional arguments are attribute/style string of IMG element.
If it is digits and unit, treat as size (ex. 120, 25%) of IMG.
If it is 'right', 'left', 'top' or 'bottom', treat as align of IMG.
if it is key=value style, treat as attribute of IMG.
if it is key:value style, treat as style of IMG.

Ex.
  [[Image(photo.jpg)]]                           # simplest
  [[Image(photo.jpg, 120px)]]                    # with size
  [[Image(photo.jpg, right)]]                    # aligned by keyword
  [[Image(photo.jpg, align=right)]]              # aligned by attribute
  [[Image(photo.jpg, float:right)]]              # aligned by style
  [[Image(photo.jpg, float:right, border:solid 5px green)]]   # with any style

You can use image from other page, other ticket or other module.
  [[Image(OtherPage:foo.bmp)]]    # if current module is wiki
  [[Image(base/sub:bar.bmp)]]     # from hierarchical wiki page
  [[Image(#3:baz.bmp)]]           # if in a ticket, point to #3
  [[Image(ticket:36:boo.jpg)]]
  [[Image(source:/images/bee.jpg)]] # straight from the repository!
"""

import os
import re
import string

from trac.util import escape
from trac.Browser import BrowserModule
from trac.attachment import Attachment

def execute(hdf, txt, env):
    # args will be null if the macro is called without parenthesis.
    if not txt:
        return ''
    # parse arguments
    # we expect the 1st argument to be a filename (filespec)
    args = txt.split(',')
    if len(args) == 0:
        raise Exception("No argument.")
    filespec = args[0]
    size_re = re.compile('^[0-9]+%?$')
    align_re = re.compile('^(?:left|right|top|bottom)$')
    keyval_re = re.compile('^([-a-z0-9]+)([=:])(.*)')
    quoted_re = re.compile("^(?:&#34;|')(.*)(?:&#34;|')$")
    attr = {}
    style = {}
    for arg in args[1:]:
        arg = arg.strip()
        if size_re.search(arg):
            # 'width' keyword
            attr['width'] = arg
            continue
        if align_re.search(arg):
            # 'align' keyword
            attr['align'] = arg
            continue
        match = keyval_re.search(arg)
        if match:
            key = match.group(1)
            sep = match.group(2)
            val = match.group(3)
            m = quoted_re.search(val) # unquote &#34; character "
            if m:
                val = m.group(1)
            if sep == '=':
                attr[key] = val;
            elif sep == ':':
                style[key] = val
        print 'attributes', attr
        print 'style', style

    # parse filespec argument to get module and id if contained.
    parts = filespec.split(':')
    url = None
    if len(parts) == 3:                 # module:id:attachment
        if parts[0] in ['wiki', 'ticket']:
            module, id, file = parts
        else:
            raise Exception("%s module can't have attachments" % parts[0])
    elif len(parts) == 2:
        try:
            browser_links = [link for link,_ in BrowserModule(env).get_link_resolvers()]
        except Exception:
            browser_links = []
        if parts[0] in browser_links:   # source:path
            module, file = parts
            url = env.href.browser(file)
            raw_url = env.href.browser(file, format='raw')
            desc = filespec
        else:                           # #ticket:attachment or WikiPage:attachment
            # FIXME: do something generic about shorthand forms...
            id, file = parts
            if id and id[0] == '#':
                module = 'ticket'
                id = id[1:]
            else:
                module = 'wiki'
    elif len(parts) == 1:               # attachment
        # determine current object
        # FIXME: should be retrieved from the formatter...
        # ...and the formatter should be provided to the macro
        file = filespec
        module, id = hdf['HTTP.PathInfo'].split('/', 3)[1:]
        print module, id
        if module not in ['wiki', 'ticket']:
            raise Exception('Cannot reference local attachment from here')
    else:
        raise Exception('No filespec given')
    if not url: # this is an attachment
        attachment = Attachment(env, module, id, file)
        url = attachment.href()
        raw_url = attachment.href(format='raw')
        desc = attachment.description
    for key in ['title', 'alt']:
        if desc and not attr.has_key(key):
            attr[key] = desc
    a_style = 'padding:0; border:none' # style of anchor
    img_attr = ' '.join(['%s="%s"' % x for x in attr.iteritems()])
    img_style = '; '.join(['%s:%s' % x for x in style.iteritems()])
    print img_attr, img_style
    return '<a href="%s" style="%s"><img src="%s" %s style="%s" /></a>' \
           % (url, a_style, raw_url, img_attr, img_style)
