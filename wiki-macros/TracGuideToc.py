# -*- coding: utf-8 -*-
"""
This macro shows a quick and dirty way to make a table-of-contents for a set
of wiki pages.
"""

TOC = [('TracGuide',                    'Index'),
       ('TracInstall',                  'Installation'),
       ('TracUpgrade',                  'Upgrading'),
       ('TracIni',                      'Configuration'),
       ('TracAdmin',                    'Administration'),
       ('TracBackup',                   'Backup'),
       ('TracLogging',                  'Logging'),
       ('TracPermissions' ,             'Permissions'),
       ('TracWiki',                     'The Wiki'),
       ('WikiFormatting',               'Wiki Formatting'),
       ('TracTimeline',                 'Timeline'),
       ('TracBrowser',                  'Repository Browser'),
       ('TracChangeset',                'Changesets'),
       ('TracRoadmap',                  'Roadmap'),
       ('TracTickets',                  'Tickets'),
       ('TracQuery',                    'Ticket Queries'),
       ('TracReports',                  'Reports'),
       ('TracRss',                      'RSS Support'),
       ('TracNotification',             'Notification'),
       ('TracInterfaceCustomization',   'Customization'),
       ('TracPlugins',                  'Plugins'),
       ]

def execute(hdf, args, env):
    html = '<div class="wiki-toc">' \
           '<h4>Table of Contents</h4>' \
           '<ul>'
    curpage = '%s' % hdf.getValue('wiki.page_name', '')
    lang, page = '/' in curpage and curpage.split('/', 1) or ('', curpage)
    for ref, title in TOC:
        if page == ref:
            cls =  ' class="active"'
        else:
            cls = ''
        html += '<li%s><a href="%s">%s</a></li>' \
                % (cls, env.href.wiki(lang+ref), title)
    return html + '</ul></div>'
