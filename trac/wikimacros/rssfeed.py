# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
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
# :Author: Daniel Lundin <daniel@edgewall.com>
#
#
# This module requires the 'feedparser' module by Mark Pilgrim.
# Download and install it from http://www.feedparser.org/

CSS = """
      .rssfeed {
       padding: .5em;
       margin: 0;
       background: #fcfcfa;
       border: 1px solid #e7e7d7;
      }
      .rssfeed p, .rssfeed * {
       font-size: small;
       line-height: normal;
      }
      .rssfeed h3 {
       margin: 0;
      }
      .rssfeed h3 a {
       font-size: 16px;
       border: none;
      }
      .rssfeed ul.entries {
       list-style-type: none;
       margin: 0;
       padding: 0;
      }
      .rssfeed ul.entries li.entry {
       margin: 1em;
       padding: .5em 0;
       border-top: 1px solid #e7e7d7;
      }
      .rssfeed .title {
       font-size: 13px;
       color: #000;
       padding: .1em 0;
       font-weight: bold;
       border: none;
       display: block;
      }
      .rssfeed .summary {
       clear: left;
       padding: 0 1.5em;
      }
      .rssfeed .date {
       font-size: xx-small;
       color: #ccc;
      }
"""


def rss_feed(url, num = 10):
    try:
        import feedparser
    except ImportError:
        return """
        <div id="content" class="error">
        <h3>Error: Feedparser not found</h3>
        <p class="message">
        <b>rssfeed</b> requires the 'feedparser' python module to work.<br />
        Download and install it from
        <a href="http://www.feedparser.org/">http://www.feedparser.org/</a>.
        </p>
        """
    if not (url.startswith('http://') or url.startswith('https://')):
        raise ValueError('Not a valid URL')
    ch = feedparser.parse(url)
    title = ch.feed.title
    link = ch.feed.link
    entries = ''
    i = 0
    for e in ch.entries:
        entries += '<li class="entry">'
        entries += '<div class="date">%s</div>' % e.get('modified','')
        entries += '<a class="title" href="%s">%s</a>' \
                   % (e.link, e.title)
        entries += '<div class="summary">%s</div>' % e.summary
        entries += '</li>'
        i += 1
        if i > num:
            break
    return """
    <style>%s</style>
    <div class="rssfeed">
      <h3><a href="%s">%s</a></h3>
      <ul class="entries">
        %s
      </ul>
    </div>
    """ % (CSS, link, title, entries)


def execute(hdf, arg, env):
    if hdf:
        hdf.setValue('wiki.macro.greeting', 'Hello World')
    i = arg.rfind(',')
    if i > -1:
        n_entries = int(arg[i+1:].strip())
        url = arg[:i].strip()
    else:
        n_entries = 10
        url = arg.strip()

    return rss_feed(url, n_entries)

