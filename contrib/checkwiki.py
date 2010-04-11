#!/usr/bin/python
#
# Check/update default wiki pages from the Trac project website.
#
# Note: This is a development tool used in Trac packaging/QA, not something
#       particularly useful for end-users.
#
# Author: Daniel Lundin <daniel@edgewall.com>

import httplib
import re
import sys
import getopt

# Pages to include in distribution
wiki_pages = [
 "CamelCase",
 "InterMapTxt",
 "InterTrac",
 "InterWiki",
 "PageTemplates",
 "RecentChanges",
 "TitleIndex",
 "TracAccessibility",
 "TracAdmin",
 "TracBackup",
 "TracBrowser",
 "TracCgi",
 "TracChangeset",
 "TracEnvironment",
 "TracFastCgi",
 "TracFineGrainedPermissions",
 "TracGuide",
 "TracImport",
 "TracIni",
 "TracInstall",
 "TracInterfaceCustomization",
 "TracLinks",
 "TracLogging",
 "TracModPython",
 "TracModWSGI",
 "TracNavigation",
 "TracNotification",
 "TracPermissions",
 "TracPlugins",
 "TracQuery",
 "TracReports",
 "TracRepositoryAdmin",
 "TracRevisionLog",
 "TracRoadmap",
 "TracRss",
 "TracSearch",
 "TracStandalone",
 "TracSupport",
 "TracSyntaxColoring",
 "TracTickets",
 "TracTicketsCustomFields",
 "TracTimeline",
 "TracUnicode",
 "TracUpgrade",
 "TracWiki",
 "TracWorkflow",
 "WikiDeletePage",
 "WikiFormatting",
 "WikiHtml",
 "WikiMacros",
 "WikiNewPage",
 "WikiPageNames",
 "WikiProcessors",
 "WikiRestructuredText",
 "WikiRestructuredTextLinks"
 ]

def get_page_from_file(prefix, pname):
    d = ''
    try:
        f = open(pname ,'r')
        d = f.read()
        f.close()
    except:
        print "Missing page: %s" % pname
    return d

def get_page_from_web(prefix, pname):
    host = "trac.edgewall.org"
    rfile = "/wiki/%s%s?format=txt" % (prefix, pname)
    c = httplib.HTTPConnection(host)
    c.request("GET", rfile)
    print "Getting", rfile
    r = c.getresponse()
    d = r.read()
    if r.status == 200 and d:
        f = open(pname, 'w+')
        f.write(d)
        f.close()
    else:
        print "Missing or empty page"
    c.close()
    return d

def check_links(data):
    def get_refs(t, refs=[]):
        r = "(?P<wikilink>(^|(?<=[^A-Za-z]))[!]?[A-Z][a-z/]+(?:[A-Z][a-z/]+)+)"
        m = re.search (r, t)
        if not m:
            refs.sort()
            result = []
            orf = None
            for rf in refs:
                if rf != orf:
                    result.append(rf)
                    orf = rf
            return result
        refs.append(m.group())
        return get_refs( t[m.end():], refs)
    for p in data.keys():
        links = get_refs(data[p], [])
        for l in links:
            if l not in data.keys():
                print "Broken link:  %s -> %s" % (p, l)

if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], "dCp:")
    except getopt.GetoptError:
        # print help information and exit:
        print "%s [-d] [-C] [-p prefix] [PAGE ...]" % sys.argv[0]
        print "\t-d        -- Download pages from the main project wiki."
        print "\t-C        -- Don't try to check links (it's broken anyway)"
        print "\t-p prefix -- When downloading, prepend 'prefix/' to the page."
        sys.exit()
    get_page = get_page_from_file
    prefix = ''
    check = True
    for o,a in opts:
        if o == '-d':
            get_page = get_page_from_web
        elif o == '-p':
            prefix = a+'/'
        elif o == '-C':
            check = False
    data = {}
    for p in args or wiki_pages:
        data[p] = get_page(prefix, p)
    if check:
        check_links(data)

