#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2018 Edgewall Software
# Copyright (C) 2007 Eli Carter <retracile@gmail.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import sys
import getopt
import locale

import pkg_resources
pkg_resources.require('Trac')

from trac.config import Configuration
from trac.ticket.default_workflow import parse_workflow_config

_debug = False
def debug(s):
    if _debug:
        sys.stderr.write(s)


def readconfig(filename):
    """Returns a list of raw config options"""
    config = Configuration(filename)
    rawactions = list(config.options('ticket-workflow'))
    debug("%s\n" % str(rawactions))
    if not rawactions:
        sys.stderr.write("ERROR: You don't seem to have a [ticket-workflow] "
                         "section.\n")
        sys.exit(1)
    return rawactions


class ColorScheme(object):
    # cyan, yellow are too light in color
    colors = ['black', 'blue', 'red', 'green', 'purple', 'orange',
              'darkgreen']

    def __init__(self):
        self.mapping = {}
        self.coloruse = [0] * len(self.colors)

    def get_color(self, name):
        try:
            colornum = self.mapping[name]
        except KeyError:
            self.mapping[name] = colornum = self.pick_color(name)
        self.coloruse[colornum] += 1
        return self.colors[colornum]

    def pick_color(self, name):
        """Pick a color that has not been used much so far."""
        return self.coloruse.index(min(self.coloruse))


def actions2graphviz(actions, show_ops=False, show_perms=False):
    """Returns a list of lines to be fed to graphviz."""
    # The size value makes it easier to create a useful printout.
    color_scheme = ColorScheme()
    digraph_lines = ["""
digraph G {
  center=1
  size="10,8"
  { rank=source; new [ shape=invtrapezium ] }
  { rank=sink; closed [ shape=trapezium ] }
    """]
    for action, attributes in actions.items():
        label = [attributes['label']]
        if show_ops:
            label += attributes['operations']
        if show_perms:
            label += attributes['permissions']
        if 'set_resolution' in attributes:
            label += ['(' + attributes['set_resolution'] + ')']
        for oldstate in attributes['oldstates']:
            color = color_scheme.get_color(attributes['label'])
            digraph_lines.append(
                '  "%s" -> "%s" [label="%s" color=%s fontcolor=%s]' %
                (oldstate, attributes['newstate'], '\\n'.join(label), color,
                 color))
    digraph_lines.append('}')
    return digraph_lines


def main(filename, output, show_ops=False, show_perms=False):
    # Read in the config
    rawactions = readconfig(filename)

    # Parse the config information
    actions = parse_workflow_config(rawactions)

    # Convert to graphviz
    digraph_lines = actions2graphviz(actions, show_ops, show_perms)

    # And output
    output.write(unicode.encode('\n'.join(digraph_lines),
                                locale.getpreferredencoding()))


def usage(output):
    output.write('workflow_parser [options] configfile.ini [output.dot]\n'
                 '-h --help shows this message\n'
                 '-o --operations include operations in the graph\n'
                 '-p --permissions include permissions in the graph\n')


if __name__ == '__main__':
    show_ops = False
    show_perms = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hop', ['help', 'operations',
                                                         'permissions'])
    except getopt.GetoptError:
        usage(sys.stderr)
        sys.exit(1)

    for option, argument in opts:
        if option in ('-h', '--help'):
            usage(sys.stdout)
            sys.exit(0)
        elif option in ('-o', '--operations'):
            show_ops = True
        elif option in ('-p', '--permissions'):
            show_perms = True

    if not args:
        sys.stderr.write('Syntax error: config filename required.\n')
        usage(sys.stderr)
        sys.stderr.flush()
        sys.exit(1)
    ini_filename = args[0]
    if len(args) > 1:
        output = open(args[1], 'w')
    else:
        output = sys.stdout

    main(ini_filename, output, show_ops, show_perms)
