#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 
# Copyright (C) 2003-2008 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import cmd
import locale
import os
import pkg_resources
import shlex
import StringIO
import sys
import traceback

from trac import __version__ as VERSION
from trac.admin import AdminCommandError, AdminCommandManager, PathList
from trac.core import TracError
from trac.env import Environment
from trac.util import translation
from trac.util.html import html
from trac.util.text import to_unicode, console_print, printout, printerr
from trac.util.translation import _
from trac.wiki.admin import WikiAdmin
from trac.wiki.macros import WikiMacroBase

TRAC_VERSION = pkg_resources.get_distribution('Trac').version


class TracAdmin(cmd.Cmd):
    intro = ''
    doc_header = 'Trac Admin Console %(version)s\n' \
                 'Available Commands:\n' \
                 % {'version': TRAC_VERSION}
    ruler = ''
    prompt = "Trac> "
    envname = None
    __env = None

    def __init__(self, envdir=None):
        cmd.Cmd.__init__(self)
        try:
            import readline
            delims = readline.get_completer_delims()
            for c in '-/':
                delims = delims.replace(c, '')
            readline.set_completer_delims(delims)
        except ImportError:
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
                    encoding = locale.getpreferredencoding() # sys.argv
                line = to_unicode(line, encoding)
            if self.interactive:
                line = line.replace('\\', '\\\\')
            rv = cmd.Cmd.onecmd(self, line) or 0
        except SystemExit:
            raise
        except AdminCommandError, e:
            printerr(_("Error:"), e)
            if e.show_usage:
                print
                self.do_help(e.cmd or self.arg_tokenize(line)[0])
            rv = 2
        except TracError, e:
            printerr(_("Command failed:"), e)
            rv = 2
        if not self.interactive:
            return rv

    def run(self):
        self.interactive = True
        printout(_("""Welcome to trac-admin %(version)s
Interactive Trac administration console.
Copyright (c) 2003-2008 Edgewall Software

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
        try:
            self.__env = Environment(self.envname)
        except:
            return 0
        return 1

    def env_open(self):
        try:
            if not self.__env:
                self.__env = Environment(self.envname)
            return self.__env
        except Exception, e:
            printerr(_("Failed to open environment."), e)
            traceback.print_exc()
            sys.exit(1)

    ##
    ## Utility methods
    ##

    def arg_tokenize(self, argstr):
        """`argstr` is an `unicode` string

        ... but shlex is not unicode friendly.
        """
        return [unicode(token, 'utf-8')
                for token in shlex.split(argstr.encode('utf-8'))] or ['']

    def word_complete(self, text, words):
        words = list(set(a for a in words if a.startswith(text)))
        if len(words) == 1:
            return [words[0] + ' ']     # Only one choice, skip to next arg
        return words

    def path_complete(self, text, words):
        words = list(set(a for a in words if a.startswith(text)))
        if len(words) == 1 and not os.path.isdir(words[0]):
            return [words[0] + ' ']
        return words
        
    @classmethod
    def print_doc(cls, docs, stream=None):
        if stream is None:
            stream = sys.stdout
        if not docs: return
        for cmd, doc in docs:
            if doc:
                console_print(stream, cmd)
                console_print(stream, '\t-- %s\n' % doc)

    ##
    ## Command dispatcher
    ##
    
    def completenames(self, text, line, begidx, endidx):
        names = cmd.Cmd.completenames(self, text, line, begidx, endidx)
        cmd_mgr = AdminCommandManager(self.env_open())
        names.extend(cmd_mgr.get_commands())
        return self.word_complete(text, names)
        
    def completedefault(self, text, line, begidx, endidx):
        args = self.arg_tokenize(line)
        if line[-1] == ' ':     # Space starts new argument
            args.append('')
        cmd_mgr = AdminCommandManager(self.env_open())
        try:
            comp = cmd_mgr.complete_command(args)
        except Exception, e:
            printerr()
            printerr(_('Completion error:'), e)
            # Uncomment the following line to get the full traceback
#            traceback.print_exc()
            return []
        if isinstance(comp, PathList):
            return self.path_complete(text, comp)
        else:
            return self.word_complete(text, comp)
        
    def default(self, line):
        args = self.arg_tokenize(line)
        cmd_mgr = AdminCommandManager(self.env_open())
        return cmd_mgr.execute_command(*args)

    ##
    ## Available Commands
    ##

    ## Help
    _help_help = [('help', 'Show documentation')]

    @classmethod
    def all_docs(cls, env=None):
        docs = (cls._help_help + cls._help_initenv)
        if env is not None:
            docs.extend(AdminCommandManager(env).get_command_help())
        return docs

    def do_help(self, line=None):
        arg = self.arg_tokenize(line)
        if arg[0]:
            doc = getattr(self, "_help_" + arg[0], None)
            if doc is None and self.envname is not None:
                cmd_mgr = AdminCommandManager(self.env_open())
                doc = cmd_mgr.get_command_help(' '.join(arg))
            if doc is not None:
                self.print_doc(doc)
            else:
                printerr(_("No documentation found for '%(cmd)s'", cmd=arg[0]))
        else:
            printout(_("trac-admin - The Trac Administration Console "
                       "%(version)s", version=TRAC_VERSION))
            if not self.interactive:
                print
                printout(_("Usage: trac-admin </path/to/projenv> "
                           "[command [subcommand] [option ...]]\n")
                    )
                printout(_("Invoking trac-admin without command starts "
                           "interactive mode.\n"))
            env = (self.envname is not None) and self.env_open() or None
            self.print_doc(self.all_docs(env))


    ## Quit / EOF
    _help_quit = [['quit', 'Exit the program']]
    _help_exit = _help_quit
    _help_EOF = _help_quit

    def do_quit(self, line):
        print
        sys.exit()

    do_exit = do_quit # Alias
    do_EOF = do_quit # Alias


    ## Initenv
    _help_initenv = [('initenv',
                      'Create and initialize a new environment interactively'),
                     ('initenv <projectname> <db> <repostype> <repospath>',
                      'Create and initialize a new environment from arguments')]

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
 directory. It is also possible to use an already existing
 PostgreSQL database (check the Trac documentation for the exact
 connection string syntax).
"""))
        ddb = 'sqlite:db/trac.db'
        prompt = _("Database connection string [%(default)s]> ", default=ddb)
        returnvals.append(raw_input(prompt).strip() or ddb)
        printout(_(""" 
 Please specify the type of version control system,
 By default, it will be svn.

 If you don't want to use Trac with version control integration,
 choose the default here and don\'t specify a repository directory.
 in the next question.
"""))
        drpt = 'svn'
        prompt = _("Repository type [%(default)s]> ", default=drpt)
        returnvals.append(raw_input(prompt).strip() or drpt)
        printout(_("""
 Please specify the absolute path to the version control
 repository, or leave it blank to use Trac without a repository.
 You can also set the repository location later.
"""))
        prompt = _("Path to repository [/path/to/repos]> ")
        returnvals.append(raw_input(prompt).strip())
        print
        return returnvals

    def do_initenv(self, line):
        def initenv_error(msg):
            printerr(_("Initenv for '%(env)s' failed.", env=self.envname),
                     "\n", msg)
        if self.env_check():
            initenv_error("Does an environment already exist?")
            return 2

        if os.path.exists(self.envname) and os.listdir(self.envname):
            initenv_error("Directory exists and is not empty.")
            return 2

        arg = self.arg_tokenize(line)
        inherit_file = ''
        for num, item in enumerate(arg):
            if item.startswith('--inherit='):
                inherit_file = arg.pop(num)[10:]
        arg = arg or [''] # Reset to usual empty in case we popped the only one
        project_name = None
        db_str = None
        repository_dir = None
        if len(arg) == 1 and not arg[0]:
            returnvals = self.get_initenv_args()
            project_name, db_str, repository_type, repository_dir = returnvals
        elif len(arg) != 4:
            initenv_error('Wrong number of arguments: %d' % len(arg))
            return 2
        else:
            project_name, db_str, repository_type, repository_dir = arg[:4]

        try:
            printout(_("Creating and Initializing Project"))
            options = [
                ('trac', 'database', db_str),
                ('trac', 'repository_type', repository_type),
                ('trac', 'repository_dir', repository_dir),
                ('project', 'name', project_name),
            ]
            if inherit_file:
                options.append(('inherit', 'file', inherit_file))
            try:
                self.__env = Environment(self.envname, create=True,
                                         options=options)
            except Exception, e:
                initenv_error('Failed to create environment.')
                printerr(e)
                traceback.print_exc()
                sys.exit(1)

            # Add a few default wiki pages
            printout(_(" Installing default wiki pages"))
            cnx = self.__env.get_db_cnx()
            cursor = cnx.cursor()
            pages_dir = pkg_resources.resource_filename('trac.wiki', 
                                                        'default-pages') 
            WikiAdmin(self.__env).load_pages(pages_dir, cursor)
            cnx.commit()

            if repository_dir:
                try:
                    repos = self.__env.get_repository()
                    if repos:
                        printout(_(" Indexing repository"))
                        repos.sync(self._resync_feedback)
                except TracError, e:
                    printerr(_("""
---------------------------------------------------------------------
Warning: couldn't index the repository.

This can happen for a variety of reasons: wrong repository type, 
no appropriate third party library for this repository type,
no actual repository at the specified repository path...

You can nevertheless start using your Trac environment, but 
you'll need to check again your trac.ini file and the [trac] 
repository_type and repository_path settings in order to enable
the Trac repository browser.
"""))
        except Exception, e:
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
    """Displays help for trac-admin commands.

    Examples:
    {{{
    [[TracAdminHelp]]               # all commands
    [[TracAdminHelp(wiki)]]         # all wiki commands
    [[TracAdminHelp(wiki export)]]  # the "wiki export" command
    [[TracAdminHelp(upgrade)]]      # the upgrade command
    }}}
    """

    def expand_macro(self, formatter, name, content):
        if content:
            arg = content.split(' ', 1)[0]
            doc = getattr(TracAdmin, "_help_" + arg, None)
            if doc is None:
                cmd_mgr = AdminCommandManager(self.env)
                doc = cmd_mgr.get_command_help(arg)
            if doc is None:
                raise TracError('Unknown trac-admin command "%s"' % content)
            if arg != content:
                for cmd, help in doc:
                    if cmd.startswith(content):
                        doc = [(cmd, help)]
                        break
        else:
            doc = TracAdmin.all_docs(self.env)
        buf = StringIO.StringIO()
        TracAdmin.print_doc(doc, buf)
        return html.PRE(buf.getvalue(), class_='wiki')


def run(args=None):
    """Main entry point."""
    if args is None:
        args = sys.argv[1:]
    locale = None
    try:
        import babel
        try:
            locale = babel.Locale.default()
        except babel.UnknownLocaleError:
            pass
    except ImportError:
        pass
    translation.activate(locale)
    admin = TracAdmin()
    if len(args) > 0:
        if args[0] in ('-h', '--help', 'help'):
            return admin.onecmd('help')
        elif args[0] in ('-v','--version'):
            printout(os.path.basename(sys.argv[0]), TRAC_VERSION)
        else:
            env_path = os.path.abspath(args[0])
            try:
                unicode(env_path, 'ascii')
            except UnicodeDecodeError:
                printerr(_("non-ascii environment path '%(path)s' not "
                           "supported.", path=env_path))
                sys.exit(2)
            admin.env_set(env_path)
            if len(args) > 1:
                s_args = ' '.join(["'%s'" % c for c in args[2:]])
                command = args[1] + ' ' +s_args
                return admin.onecmd(command)
            else:
                while True:
                    try:
                        admin.run()
                    except KeyboardInterrupt:
                        admin.do_quit('')
    else:
        return admin.onecmd("help")


if __name__ == '__main__':
    pkg_resources.require('Trac==%s' % VERSION)
    sys.exit(run())
