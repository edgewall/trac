#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

from __future__ import print_function

import cmd
import io
import os.path
import pkg_resources
import re
import sys
import textwrap
import traceback
from shlex import shlex
try:
    import readline
except ImportError:
    readline = None

from trac import __version__ as TRAC_VERSION
from trac.admin.api import AdminCommandError, AdminCommandManager, \
                           get_console_locale
from trac.config import Configuration
from trac.core import TracError
from trac.env import Environment
from trac.util import translation, warn_setuptools_issue
from trac.util.html import html
from trac.util.text import console_print, exception_to_unicode, \
                           getpreferredencoding, printerr, printout, \
                           raw_input, to_unicode
from trac.util.translation import _, cleandoc_, has_babel, ngettext
from trac.wiki.formatter import MacroError
from trac.wiki.macros import WikiMacroBase


class TracAdmin(cmd.Cmd):
    intro = ''
    doc_header = 'Trac Admin Console %(version)s\n' \
                 'Available Commands:\n' \
                 % {'version': TRAC_VERSION}
    ruler = ''
    prompt = "Trac> "
    envname = None
    __env = None
    needs_upgrade = None

    def __init__(self, envdir=None):
        cmd.Cmd.__init__(self)
        if readline:
            delims = readline.get_completer_delims()
            for c in '-/:()\\':
                delims = delims.replace(c, '')
            readline.set_completer_delims(delims)
        self.interactive = False
        if envdir:
            self.env_set(os.path.abspath(envdir))

    def emptyline(self):
        pass

    def onecmd(self, line):
        """`line` may be a `str` or an `unicode` object"""
        if isinstance(line, str):
            if self.interactive:
                encoding = sys.stdin.encoding
            else:
                encoding = getpreferredencoding()  # sys.argv
            line = to_unicode(line, encoding)
        if self.interactive:
            line = line.replace('\\', '\\\\')
        try:
            rv = cmd.Cmd.onecmd(self, line) or 0
        except SystemExit:
            raise
        except AdminCommandError as e:
            printerr(_("Error: %(msg)s", msg=to_unicode(e)))
            if e.show_usage:
                print()
                self.do_help(e.cmd or self.arg_tokenize(line)[0])
            rv = 2
        except TracError as e:
            printerr(exception_to_unicode(e))
            rv = 2
        except Exception as e:
            printerr(exception_to_unicode(e))
            rv = 2
            if self.env_check():
                self.env.log.error("Exception in trac-admin command: %r%s",
                                   line,
                                   exception_to_unicode(e, traceback=True))
        if not self.interactive:
            return rv

    def run(self):
        self.interactive = True
        printout(_("""Welcome to trac-admin %(version)s
Interactive Trac administration console.
Copyright (C) %(year)s Edgewall Software

Type:  '?' or 'help' for help on commands.
        """, version=TRAC_VERSION, year='2003-2019'))
        self.cmdloop()

    # Environment methods

    def env_set(self, envname, env=None):
        self.envname = envname
        self.prompt = "Trac [%s]> " % self.envname
        if env is not None:
            self.__env = env

    def env_check(self):
        if not self.__env:
            try:
                self._init_env()
            except Exception:
                return False
        return True

    @property
    def env(self):
        if not self.__env:
            try:
                self._init_env()
            except Exception as e:
                printerr(_("Failed to open environment: %(err)s",
                           err=exception_to_unicode(e, traceback=True)))
                sys.exit(1)
        return self.__env

    def _init_env(self):
        self.__env = env = Environment(self.envname)
        # fix language according to env settings
        if has_babel:
            negotiated = get_console_locale(env)
            if negotiated:
                translation.activate(negotiated)

    # Utility methods

    @property
    def cmd_mgr(self):
        return AdminCommandManager(self.env)

    def arg_tokenize(self, argstr):
        """`argstr` is an `unicode` string

        ... but shlex is not unicode friendly.
        """
        lex = shlex(argstr.encode('utf-8'), posix=True)
        lex.whitespace_split = True
        lex.commenters = ''
        if os.name == 'nt':
            lex.escape = ''
        return [unicode(token, 'utf-8') for token in lex] or ['']

    def word_complete(self, text, words):
        words = list({a for a in words if a.startswith(text)})
        if len(words) == 1:
            words[0] += ' '     # Only one choice, skip to next arg
        return words

    @staticmethod
    def split_help_text(text):
        paragraphs = re.split(r'(?m)(?:^[ \t]*\n)+', text)
        return [re.sub(r'(?m)\s+', ' ', each.strip()) for each in paragraphs]

    @classmethod
    def print_doc(cls, docs, stream=None, short=False, long=False):
        if stream is None:
            stream = sys.stdout
        docs = [doc for doc in docs if doc[2]]
        if not docs:
            return
        if short:
            max_len = max(len(doc[0]) for doc in docs)
            for cmd, args, doc in docs:
                paragraphs = cls.split_help_text(doc)
                console_print(stream, '%s  %s' % (cmd.ljust(max_len),
                                                  paragraphs[0]))
        else:
            for cmd, args, doc in docs:
                paragraphs = cls.split_help_text(doc)
                console_print(stream, '%s %s\n' % (cmd, args))
                console_print(stream, '    %s\n' % paragraphs[0])
                if (long or len(docs) == 1) and len(paragraphs) > 1:
                    for paragraph in paragraphs[1:]:
                        console_print(stream,
                                      textwrap.fill(paragraph, 79,
                                                    initial_indent='    ',
                                                    subsequent_indent='    ')
                                      + '\n')

    # Command dispatcher

    def complete_line(self, text, line, cmd_only=False):
        args = self.arg_tokenize(line)
        if line and line[-1] == ' ':    # Space starts new argument
            args.append('')
        comp = []
        if self.env_check():
            try:
                comp = self.cmd_mgr.complete_command(args, cmd_only)
            except Exception as e:
                printerr()
                printerr(_('Completion error: %(err)s',
                           err=exception_to_unicode(e)))
                self.env.log.error("trac-admin completion error: %s",
                                   exception_to_unicode(e, traceback=True))
        if len(args) == 1:
            comp.extend(name[3:] for name in self.get_names()
                        if name.startswith('do_'))
        try:
            return comp.complete(text)
        except AttributeError:
            return self.word_complete(text, comp)

    def completenames(self, text, line, begidx, endidx):
        return self.complete_line(text, line, True)

    def completedefault(self, text, line, begidx, endidx):
        return self.complete_line(text, line)

    def default(self, line):
        try:
            if not self.__env:
                self._init_env()
            if self.needs_upgrade is None:
                self.needs_upgrade = self.__env.needs_upgrade()
        except TracError as e:
            raise AdminCommandError(to_unicode(e))
        except Exception as e:
            raise AdminCommandError(exception_to_unicode(e))
        args = self.arg_tokenize(line)
        if args[0] == 'upgrade':
            self.needs_upgrade = None
        elif self.needs_upgrade:
            raise TracError(_('The Trac Environment needs to be upgraded. '
                              'Run:\n\n  trac-admin "%(path)s" upgrade',
                              path=self.envname))
        return self.cmd_mgr.execute_command(*args)

    # Available Commands

    # Help
    _help_help = [('help', '', 'Show documentation')]

    @classmethod
    def all_docs(cls, env=None):
        docs = (cls._help_help + cls._help_initenv)
        if env is not None:
            docs.extend(AdminCommandManager(env).get_command_help())
        return docs

    def complete_help(self, text, line, begidx, endidx):
        return self.complete_line(text, line[5:], True)

    def do_help(self, line=None):
        arg = self.arg_tokenize(line)
        if arg[0]:
            cmd_mgr = None
            doc = getattr(self, "_help_" + arg[0], None)
            if doc is None and self.env_check():
                cmd_mgr = self.cmd_mgr
                doc = cmd_mgr.get_command_help(arg)
            if doc:
                self.print_doc(doc)
            else:
                printerr(_("No documentation found for '%(cmd)s'."
                           " Use 'help' to see the list of commands.",
                           cmd=' '.join(arg)))
                cmds = None
                if cmd_mgr:
                    cmds = cmd_mgr.get_similar_commands(arg[0])
                if cmds:
                    printout('')
                    printout(ngettext("Did you mean this?",
                                      "Did you mean one of these?",
                                      len(cmds)))
                    for cmd in cmds:
                        printout('    ' + cmd)
        else:
            printout(_("trac-admin - The Trac Administration Console "
                       "%(version)s", version=TRAC_VERSION))
            if not self.interactive:
                print()
                printout(_("Usage: trac-admin </path/to/projenv> "
                           "[command [subcommand] [option ...]]\n"))
                printout(_("Invoking trac-admin without command starts "
                           "interactive mode.\n"))
            env = self.env if self.env_check() else None
            self.print_doc(self.all_docs(env), short=True)

    # Quit / EOF
    _help_quit = [('quit', '', 'Exit the program')]
    _help_exit = _help_quit
    _help_EOF = _help_quit

    def do_quit(self, line):
        print()
        sys.exit()

    do_exit = do_quit  # Alias
    do_EOF = do_quit  # Alias

    # Initenv
    _help_initenv = [
        ('initenv', '[<projectname> <db>]',
         """Create and initialize a new environment

         If no arguments are given, then the required parameters are requested
         interactively unless the optional argument `--config` is specified.

         One or more optional arguments --inherit=PATH can be used to specify
         the "[inherit] file" option at environment creation time, so that only
         the options not already specified in one of the global configuration
         files are written to the conf/trac.ini file of the newly created
         environment. Relative paths are resolved relative to the "conf"
         directory of the new environment.

         The optional argument --config=PATH can be used to specify a
         configuration file that is used to populate the environment
         configuration. The arguments <projectname>, <db> and any other
         arguments passed in the invocation are optional, but if specified
         will override values in the configuration file.
         """)]

    def do_initdb(self, line):
        self.do_initenv(line)

    def get_initenv_args(self):
        returnvals = []
        printout(_("""
Trac will first ask a few questions about your environment
in order to initialize and prepare the project database.

 Please enter the name of your project.
 This name will be used in page titles and descriptions.
"""))
        dp = 'My Project'
        returnvals.append(raw_input(_("Project Name [%(default)s]> ",
                                      default=dp)).strip() or dp)
        printout(_("""
 Please specify the connection string for the database. By default,
 a local SQLite database is created in the environment directory.
 It is also possible to use an existing MySQL or PostgreSQL database
 (check the Trac documentation for the connection string syntax).
"""))
        ddb = 'sqlite:db/trac.db'
        prompt = _("Database connection string [%(default)s]> ", default=ddb)
        returnvals.append(raw_input(prompt).strip() or ddb)
        print()
        return returnvals

    def do_initenv(self, line):
        def initenv_error(msg):
            printerr(_("Initenv for '%(env)s' failed.", env=self.envname),
                     "\n%s" % msg)
        if self.env_check():
            initenv_error(_("Does an environment already exist?"))
            return 2

        printout(_("Creating a new Trac environment at %(envname)s",
                   envname=self.envname))

        arg = self.arg_tokenize(line)
        inherit_paths = []
        config_file_path = None
        default_data = True
        i = 0
        while i < len(arg):
            item = arg[i]
            if item.startswith('--inherit='):
                inherit_paths.append(arg.pop(i)[10:])
            elif item.startswith('--config='):
                config_file_path = arg.pop(i)[9:]
            elif item == '--no-default-data':
                arg.pop(i)
                default_data = False
            else:
                i += 1
        config = None
        if config_file_path:
            if not os.path.exists(config_file_path):
                initenv_error(_("The file specified in the --config argument "
                                "does not exist: %(path)s.",
                                path=config_file_path))
                return 2
            try:
                config = Configuration(config_file_path)
            except TracError as e:
                initenv_error(e)
                return 2
        arg = arg or ['']  # Reset to usual empty in case we popped the only one
        if len(arg) == 1 and not arg[0] and not config:
            project_name, db_str = self.get_initenv_args()
        elif len(arg) < 2 and config:
            project_name = db_str = None
            if arg[0]:
                project_name = arg[0]
        elif len(arg) == 2:
            project_name, db_str = arg
        else:
            initenv_error('Wrong number of arguments: %d' % len(arg))
            return 2

        options = []
        if config:
            for section in config.sections(defaults=False):
                options.extend((section, option, value)
                               for option, value
                               in config.options(section))
        if project_name is not None:
            options.append(('project', 'name', project_name))
        if db_str is not None:
            options.append(('trac', 'database', db_str))

        if inherit_paths:
            options.append(('inherit', 'file',
                            ",\n      ".join(inherit_paths)))

        try:
            self.__env = Environment(self.envname, create=True, options=options,
                                     default_data=default_data)
        except TracError as e:
            initenv_error(e)
            return 2
        except Exception as e:
            initenv_error(_('Failed to create environment.'))
            printerr(e)
            traceback.print_exc()
            sys.exit(1)

        printout(_("""
Project environment for '%(project_name)s' created.

You may configure the environment by editing the file:

  %(config_path)s

You can run the Trac standalone web server `tracd` and point
your browser to http://localhost:8000/%(project_dir)s.

  tracd --port 8000 %(project_path)s

Navigate to "Help/Guide" to browse the documentation for Trac,
including information on further setup (such as deploying Trac
to a real web server).

The latest documentation can also be found on the project
website:

  https://trac.edgewall.org/
""", project_name=project_name, project_path=self.envname,
           project_dir=os.path.basename(self.envname),
           config_path=self.__env.config_file_path))


class TracAdminHelpMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_("""
    Display help for trac-admin commands.

    Examples:
    {{{
    [[TracAdminHelp]]               # all commands
    [[TracAdminHelp(wiki)]]         # all wiki commands
    [[TracAdminHelp(wiki export)]]  # the "wiki export" command
    [[TracAdminHelp(upgrade)]]      # the upgrade command
    }}}
    """)

    def expand_macro(self, formatter, name, content, args=None):
        if content:
            arg = content.strip().split()
            doc = getattr(TracAdmin, "_help_" + arg[0], None)
            if doc is None:
                cmd_mgr = AdminCommandManager(self.env)
                doc = cmd_mgr.get_command_help(arg)
            if not doc:
                raise MacroError(_('Unknown trac-admin command '
                                   '"%(command)s"', command=content))
        else:
            doc = TracAdmin.all_docs(self.env)
        buf = io.BytesIO()
        TracAdmin.print_doc(doc, buf, long=True)
        return html.PRE(buf.getvalue().decode('utf-8'), class_='wiki')


def _quote_args(args):
    def quote(arg):
        if arg.isalnum():
            return arg
        return '"\'"'.join("'%s'" % v for v in arg.split("'"))
    return [quote(arg) for arg in args]


def _run(args):
    if args is None:
        args = sys.argv[1:]
    warn_setuptools_issue()
    admin = TracAdmin()
    if args:
        if args[0] in ('-h', '--help', 'help'):
            return admin.onecmd(' '.join(_quote_args(['help'] + args[1:])))
        elif args[0] in ('-v', '--version'):
            printout(os.path.basename(sys.argv[0]), TRAC_VERSION)
        else:
            env_path = os.path.abspath(args[0])
            try:
                unicode(env_path, 'ascii')
            except UnicodeDecodeError:
                printerr(_("Non-ascii environment path '%(path)s' not "
                           "supported.", path=to_unicode(env_path)))
                return 2
            admin.env_set(env_path)
            if len(args) > 1:
                return admin.onecmd(' '.join(_quote_args(args[1:])))
            else:
                while True:
                    try:
                        admin.run()
                    except KeyboardInterrupt:
                        admin.do_quit('')
    else:
        return admin.onecmd("help")


def run(args=None):
    """Main entry point."""
    translation.activate(get_console_locale())
    try:
        return _run(args)
    finally:
        translation.deactivate()


if __name__ == '__main__':
    pkg_resources.require('Trac==%s' % TRAC_VERSION)
    sys.exit(run())
