#!/usr/bin/env python
# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003 Edgewall Software
# Copyright (C) 2003 Jonas Borgström <jonas@edgewall.com>
#
# svntrac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# svntrac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import sys
import sqlite

def usage():
    print 'usage: %s <command>' % sys.argv[0]
    print '\n Available commands:\n'
    print '   component list'
    print '   component add <name> <owner>'
    print '   component remove <name>'
    print '   component set owner <name> <new_owner>'
    print

def open_db(name):
    try:
        return sqlite.connect (name)
    except Exception, e:
        print 'Failed to open/create database.'
        sys.exit(1)

def cmd_component_list():
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    cursor.execute('SELECT name, owner FROM component')
    print 'Name                 Owner'
    print '=========================='
    while 1:
        row = cursor.fetchone()
        if row == None:
            break
        print '%-20s %-20s' % (row[0], row[1])

def cmd_component_add():
    name = sys.argv[4]
    owner = sys.argv[5]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('INSERT INTO component VALUES(%s, %s)',
                       name, owner)
        cnx.commit()
    except:
        print 'Component addition failed'

def cmd_component_remove():
    name = sys.argv[4]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('DELETE FROM component WHERE name=%s',
                       name)
        cnx.commit()
    except:
        print 'Component removal failed'

def cmd_component_set_owner():
    name = sys.argv[5]
    owner = sys.argv[6]
    cnx = open_db(sys.argv[1])
    cursor = cnx.cursor()
    try:
        cursor.execute('UPDATE component SET owner=%s WHERE name=%s',
                       owner, name)
        cnx.commit()
    except:
        print 'Owner change failed'

def main():
    if sys.argv[2:] == ['component', 'list']:
        cmd_component_list()
    elif sys.argv[2:4] == ['component', 'add'] and len(sys.argv) == 6:
        cmd_component_add()
    elif sys.argv[2:4] == ['component', 'remove'] and len(sys.argv) == 5:
        cmd_component_remove()
    elif sys.argv[2:5] == ['component', 'set', 'owner'] and len(sys.argv) == 7:
        cmd_component_set_owner()
    else:
        usage()

if __name__ == '__main__':
    main()
