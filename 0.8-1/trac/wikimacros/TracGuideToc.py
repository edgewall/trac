# -*- coding: iso8859-1 -*-
"""
This macro shows a quick and dirty way to make a table-of-contents for a set
of wiki pages.
"""

TOC = [('TracGuide',        'Index'),
       ('TracInstall',      'Installation'),
       ('TracUpgrade',      'Upgrading'),
       ('TracIni',          'Configuration'),
       ('TracAdmin',        'Administration'),
       ('TracBackup',       'Backup'),
       ('TracLogging',      'Logging'),
       ('TracPermissions' , 'Permissions'),
       ('TracWiki',         'The Wiki'),
       ('WikiFormatting',   'Wiki Formatting'),
       ('TracBrowser',      'The Browser'),
       ('TracRoadmap',      'The Roadmap'),
       ('TracChangeset',    'Changesets'),
       ('TracTickets',      'Tickets'),
       ('TracReports',      'Reports'),
       ('TracQuery',        'Custom Queries'),
       ('TracTimeline',     'Timeline'),
       ('TracRss',          'RSS Support'),
       ('TracNotification', 'Notification'),
       ]

def execute(hdf, args, env):
    html = '<div class="wiki-toc">' \
           '<h4>Table of Contents</h4>' \
           '<ul>'
    curpage =  '%s' % hdf.getValue('args.page', '')
    for ref,title in TOC:
        if curpage == ref:
            cls =  ' class="active"'
        else:
            cls = ''
        html += '<li%s><a href="%s">%s</a></li>' \
                % (cls, env.href.wiki(ref), title)
    return html + '</ul></div>'
