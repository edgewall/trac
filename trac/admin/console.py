#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2010 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from __future__ import print_function

import cmd
import os.path
import pkg_resources
from shlex import shlex
import StringIO
import sys
import traceback

from trac import __version__ as VERSION
from trac.admin.api import AdminCommandError, AdminCommandManager, \
                           get_console_locale
from trac.config import Configuration
from trac.core import TracError
from trac.env import Environment
from trac.ticket.model import *
from trac.util import translation, warn_setuptools_issue
from trac.util.html import html
from trac.util.text import console_print, exception_to_unicode, printout, \
                           printerr, raw_input, to_unicode, \
                           getpreferredencoding
from trac.util.translation import _, ngettext, has_babel, cleandoc_
from trac.versioncontrol.api import RepositoryManager
from trac.web.chrome import default_mainnav_order, default_metanav_order
from trac.wiki.admin import WikiAdmin
from trac.wiki.formatter import MacroError
from trac.wiki.macros import WikiMacroBase


TRAC_VERSION = pkg_resources.get_distribution('Trac').version
rl_completion_suppress_append = None


def find_readline_lib():
    """Return the name (and possibly the full path) of the readline library
    linked to the readline module.
    """
    import readline
    with open(readline.__file__, "rb") as f:
        data = f.read()
    import re
    m = re.search('\0([^\0]*libreadline[^\0]*)\0', data)
    if m:
        return m.group(1)
    return None


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
        try:
            import readline
            delims = readline.get_completer_delims()
            for c in '-/:()\\':
                delims = delims.replace(c, '')
            readline.set_completer_delims(delims)

            # Work around trailing space automatically inserted by libreadline
            # until Python gets fixed, see http://bugs.python.org/issue5833
            import ctypes
            lib_name = find_readline_lib()
            if lib_name is not None:
                lib = ctypes.cdll.LoadLibrary(lib_name)
                global rl_completion_suppress_append
                rl_completion_suppress_append = ctypes.c_int.in_dll(lib,
                                            "rl_completion_suppress_append")
        except Exception:
            pass
        self.interactive = False
        if envdir:
            self.env_set(os.path.abspath(envdir))

    def emptyline(self):
        pass

    def onecmd(self, line):
        """`line` may be a `str` or an `unicode` object"""
        try:
            if isinstance(line, str):
                if self.interactive:
                    encoding = sys.stdin.encoding
                else:
                    encoding = getpreferredencoding() # sys.argv
                line = to_unicode(line, encoding)
            if self.interactive:
                line = line.replace('\\', '\\\\')
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
Copyright (C) 2003-2013 Edgewall Software

Type:  '?' or 'help' for help on commands.
        """, version=TRAC_VERSION))
        self.cmdloop()

    ##
    ## Environment methods
    ##

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
        try:
            if not self.__env:
                self._init_env()
            return self.__env
        except Exception as e:
            printerr(_("Failed to open environment: %(err)s",
                       err=exception_to_unicode(e, traceback=True)))
            sys.exit(1)

    def _init_env(self):
        self.__env = env = Environment(self.envname)
        negotiated = None
        # fixup language according to env settings
        if has_babel:
            negotiated = get_console_locale(env)
            if negotiated:
                translation.activate(negotiated)

    ##
    ## Utility methods
    ##

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
        words = list(set(a for a in words if a.startswith(text)))
        if len(words) == 1:
            words[0] += ' '     # Only one choice, skip to next arg
        return words

    @staticmethod
    def split_help_text(text):
        import re
        paragraphs = re.split(r'(?m)(?:^[ \t]*\n){1,}', text)
        return [re.sub(r'(?m)\s+', ' ', each.strip())
                for each in paragraphs]

    @classmethod
    def print_doc(cls, docs, stream=None, short=False, long=False):
        if stream is None:
            stream = sys.stdout
        docs = [doc for doc in docs if doc[2]]
        if not docs:
            return
        if short:
            max_len = max(len(doc[0]) for doc in docs)
            for (cmd, args, doc) in docs:
                paragraphs = cls.split_help_text(doc)
                console_print(stream, '%s  %s' % (cmd.ljust(max_len),
                                                  paragraphs[0]))
        else:
            import textwrap
            for (cmd, args, doc) in docs:
                paragraphs = cls.split_help_text(doc)
                console_print(stream, '%s %s\n' % (cmd, args))
                console_print(stream, '    %s\n' % paragraphs[0])
                if (long or len(docs) == 1) and len(paragraphs) > 1:
                    for paragraph in paragraphs[1:]:
                        console_print(stream, textwrap.fill(paragraph, 79,
                            initial_indent='    ', subsequent_indent='    ')
                            + '\n')

    ##
    ## Command dispatcher
    ##

    def complete_line(self, text, line, cmd_only=False):
        if rl_completion_suppress_append is not None:
            rl_completion_suppress_append.value = 1
        args = self.arg_tokenize(line)
        if line and line[-1] == ' ':    # Space starts new argument
            args.append('')
        if self.env_check():
            try:
                comp = self.cmd_mgr.complete_command(args, cmd_only)
            except Exception as e:
                printerr()
                printerr(_('Completion error: %(err)s',
                           err=exception_to_unicode(e)))
                self.env.log.error("trac-admin completion error: %s",
                                   exception_to_unicode(e, traceback=True))
                comp = []
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

    ##
    ## Available Commands
    ##

    ## Help
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
                           "[command [subcommand] [option ...]]\n")
                    )
                printout(_("Invoking trac-admin without command starts "
                           "interactive mode.\n"))
            env = self.env if self.env_check() else None
            self.print_doc(self.all_docs(env), short=True)


    ## Quit / EOF
    _help_quit = [('quit', '', 'Exit the program')]
    _help_exit = _help_quit
    _help_EOF = _help_quit

    def do_quit(self, line):
        print()
        sys.exit()

    do_exit = do_quit # Alias
    do_EOF = do_quit # Alias


    ## Initenv
    _help_initenv = [
        ('initenv', '[<projectname> <db> [<repostype> <repospath>]]',
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
        printout(_("Creating a new Trac environment at %(envname)s",
                   envname=self.envname))
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
 Please specify the connection string for the database to use.
 By default, a local SQLite database is created in the environment
 directory. It is also possible to use an existing MySQL or
 PostgreSQL database (check the Trac documentation for the exact
 connection string syntax).
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

        if os.path.exists(self.envname) and os.listdir(self.envname):
            initenv_error(_("Directory exists and is not empty."))
            return 2

        if not os.path.exists(os.path.dirname(self.envname)):
            initenv_error(_("Base directory '%(env)s' does not exist. Please "
                            "create it manually and retry.",
                            env=os.path.dirname(self.envname)))
            return 2

        arg = self.arg_tokenize(line)
        inherit_paths = []
        config_file_path = None
        i = 0
        while i < len(arg):
            item = arg[i]
            if item.startswith('--inherit='):
                inherit_paths.append(arg.pop(i)[10:])
            elif item.startswith('--config='):
                config_file_path = arg.pop(i)[9:]
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
        arg = arg or [''] # Reset to usual empty in case we popped the only one
        repository_type = None
        repository_dir = None
        if len(arg) == 1 and not arg[0] and not config:
            project_name, db_str = self.get_initenv_args()
        elif len(arg) < 2 and config:
            project_name = db_str = None
            if arg[0]:
                project_name = arg[0]
        elif len(arg) == 2:
            project_name, db_str = arg
        elif len(arg) == 4:
            project_name, db_str, repository_type, repository_dir = arg
        else:
            initenv_error('Wrong number of arguments: %d' % len(arg))
            return 2

        try:
            printout(_("Creating and Initializing Project"))
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

            def add_nav_order_options(section, default):
                for i, name in enumerate(default, 1):
                    options.append((section, name + '.order', float(i)))
            add_nav_order_options('mainnav', default_mainnav_order)
            add_nav_order_options('metanav', default_metanav_order)
            if repository_dir:
                options.extend([
                    ('repositories', '.type', repository_type),
                    ('repositories', '.dir', repository_dir),
                ])
            if inherit_paths:
                options.append(('inherit', 'file',
                                ",\n      ".join(inherit_paths)))
            try:
                self.__env = Environment(self.envname, create=True,
                                         options=options)
            except Exception as e:
                initenv_error(_('Failed to create environment.'))
                printerr(e)
                traceback.print_exc()
                sys.exit(1)

            # Add a few default wiki pages
            printout(_(" Installing default wiki pages"))
            pages_dir = pkg_resources.resource_filename('trac.wiki',
                                                        'default-pages')
            WikiAdmin(self.__env).load_pages(pages_dir)

            if repository_dir:
                try:
                    repos = RepositoryManager(self.__env).get_repository('')
                    if repos:
                        printout(_(" Indexing default repository"))
                        repos.sync(self._resync_feedback)
                except TracError as e:
                    printerr(_("""
---------------------------------------------------------------------
Warning: couldn't index the default repository.

This can happen for a variety of reasons: wrong repository type,
no appropriate third party library for this repository type,
no actual repository at the specified repository path...

You can nevertheless start using your Trac environment, but
you'll need to check again your trac.ini file and the [trac]
repository_type and repository_path settings.
"""))
        except Exception as e:
            initenv_error(to_unicode(e))
            traceback.print_exc()
            return 2

        printout(_("""
---------------------------------------------------------------------
Project environment for '%(project_name)s' created.

You may now configure the environment by editing the file:

  %(config_path)s

If you'd like to take this new project environment for a test drive,
try running the Trac standalone web server `tracd`:

  tracd --port 8000 %(project_path)s

Then point your browser to http://localhost:8000/%(project_dir)s.
There you can also browse the documentation for your installed
version of Trac, including information on further setup (such as
deploying Trac to a real web server).

The latest documentation can also always be found on the project
website:

  http://trac.edgewall.org/

Congratulations!
""", project_name=project_name, project_path=self.envname,
           project_dir=os.path.basename(self.envname),
           config_path=os.path.join(self.envname, 'conf', 'trac.ini')))

    def _resync_feedback(self, rev):
        sys.stdout.write(' [%s]\r' % rev)
        sys.stdout.flush()


class TracAdminHelpMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Display help for trac-admin commands.

    Examples:
    {{{
    [[TracAdminHelp]]               # all commands
    [[TracAdminHelp(wiki)]]         # all wiki commands
    [[TracAdminHelp(wiki export)]]  # the "wiki export" command
    [[TracAdminHelp(upgrade)]]      # the upgrade command
    }}}
    """)

    def expand_macro(self, formatter, name, content):
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
        buf = StringIO.StringIO()
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
    if sys.flags.optimize != 0:
        printerr(_("Python with optimizations is not supported."))
        return 2
    admin = TracAdmin()
    if args:
        if args[0] in ('-h', '--help', 'help'):
            return admin.onecmd(' '.join(_quote_args(['help'] + args[1:])))
        elif args[0] in ('-v','--version'):
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
    pkg_resources.require('Trac==%s' % VERSION)
    sys.exit(run())
