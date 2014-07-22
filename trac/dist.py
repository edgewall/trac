# -*- coding: utf-8 -*-
#
# Copyright (C) 2011 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""Extra commands for setup.py.

In addition to providing a few extra command classes in `l10n_cmdclass`,
we also modify the standard `distutils.command.build` and
`setuptools.command.install_lib` classes so that the relevant l10n commands
for compiling catalogs are issued upon install.
"""

from __future__ import with_statement

from StringIO import StringIO
from itertools import izip
import os
import re
from tokenize import generate_tokens, COMMENT, NAME, OP, STRING

from distutils import log
from distutils.cmd import Command
from distutils.command.build import build as _build
from distutils.errors import DistutilsOptionError
from setuptools.command.install_lib import install_lib as _install_lib

try:
    from babel.messages.catalog import TranslationError
    from babel.messages.extract import extract_javascript
    from babel.messages.frontend import extract_messages, init_catalog, \
                                        compile_catalog, update_catalog
    from babel.messages.pofile import read_po
    from babel.support import Translations
    from babel.util import parse_encoding

    _GENSHI_MARKUP_SEARCH = re.compile(r'\[[0-9]+:').search


    _DEFAULT_KWARGS_MAPS = {
        'Option': {'doc': 4},
        'BoolOption': {'doc': 4},
        'IntOption': {'doc': 4},
        'FloatOption': {'doc': 4},
        'ListOption': {'doc': 6},
        'ChoiceOption': {'doc': 4},
        'PathOption': {'doc': 4},
        'ExtensionOption': {'doc': 5},
        'OrderedExtensionsOption': {'doc': 6},
    }

    _DEFAULT_CLEANDOC_KEYWORDS = (
        'ConfigSection', 'Option', 'BoolOption', 'IntOption', 'FloatOption',
        'ListOption', 'ChoiceOption', 'PathOption', 'ExtensionOption',
        'OrderedExtensionsOption', 'cleandoc_',
    )

    def extract_python(fileobj, keywords, comment_tags, options):
        """Extract messages from Python source code, This is patched
        extract_python from Babel to support keyword argument mapping.

        `kwargs_maps` option: names of keyword arguments will be mapping to
        index of messages array.

        `cleandoc_keywords` option: a list of keywords to clean up the
        extracted messages with `cleandoc`.
        """
        from trac.util.compat import cleandoc

        funcname = lineno = message_lineno = None
        kwargs_maps = func_kwargs_map = None
        call_stack = -1
        buf = []
        messages = []
        messages_kwargs = {}
        translator_comments = []
        in_def = in_translator_comments = False
        comment_tag = None

        encoding = str(parse_encoding(fileobj) or
                       options.get('encoding', 'iso-8859-1'))
        kwargs_maps = _DEFAULT_KWARGS_MAPS.copy()
        if 'kwargs_maps' in options:
            kwargs_maps.update(options['kwargs_maps'])
        cleandoc_keywords = set(_DEFAULT_CLEANDOC_KEYWORDS)
        if 'cleandoc_keywords' in options:
            cleandoc_keywords.update(options['cleandoc_keywords'])

        tokens = generate_tokens(fileobj.readline)
        tok = value = None
        for _ in tokens:
            prev_tok, prev_value = tok, value
            tok, value, (lineno, _), _, _ = _
            if call_stack == -1 and tok == NAME and value in ('def', 'class'):
                in_def = True
            elif tok == OP and value == '(':
                if in_def:
                    # Avoid false positives for declarations such as:
                    # def gettext(arg='message'):
                    in_def = False
                    continue
                if funcname:
                    message_lineno = lineno
                    call_stack += 1
                kwarg_name = None
            elif in_def and tok == OP and value == ':':
                # End of a class definition without parens
                in_def = False
                continue
            elif call_stack == -1 and tok == COMMENT:
                # Strip the comment token from the line
                value = value.decode(encoding)[1:].strip()
                if in_translator_comments and \
                        translator_comments[-1][0] == lineno - 1:
                    # We're already inside a translator comment, continue
                    # appending
                    translator_comments.append((lineno, value))
                    continue
                # If execution reaches this point, let's see if comment line
                # starts with one of the comment tags
                for comment_tag in comment_tags:
                    if value.startswith(comment_tag):
                        in_translator_comments = True
                        translator_comments.append((lineno, value))
                        break
            elif funcname and call_stack == 0:
                if tok == OP and value == ')':
                    if buf:
                        message = ''.join(buf)
                        if kwarg_name in func_kwargs_map:
                            messages_kwargs[kwarg_name] = message
                        else:
                            messages.append(message)
                        del buf[:]
                    else:
                        messages.append(None)

                    for name, message in messages_kwargs.iteritems():
                        if name not in func_kwargs_map:
                            continue
                        index = func_kwargs_map[name]
                        while index >= len(messages):
                            messages.append(None)
                        messages[index - 1] = message

                    if funcname in cleandoc_keywords:
                        messages = [m and cleandoc(m) for m in messages]
                    if len(messages) > 1:
                        messages = tuple(messages)
                    else:
                        messages = messages[0]
                    # Comments don't apply unless they immediately preceed the
                    # message
                    if translator_comments and \
                            translator_comments[-1][0] < message_lineno - 1:
                        translator_comments = []

                    yield (message_lineno, funcname, messages,
                           [comment[1] for comment in translator_comments])

                    funcname = lineno = message_lineno = None
                    kwarg_name = func_kwargs_map = None
                    call_stack = -1
                    messages = []
                    messages_kwargs = {}
                    translator_comments = []
                    in_translator_comments = False
                elif tok == STRING:
                    # Unwrap quotes in a safe manner, maintaining the string's
                    # encoding
                    # https://sourceforge.net/tracker/?func=detail&atid=355470&
                    # aid=617979&group_id=5470
                    value = eval('# coding=%s\n%s' % (encoding, value),
                                 {'__builtins__':{}}, {})
                    if isinstance(value, str):
                        value = value.decode(encoding)
                    buf.append(value)
                elif tok == OP and value == '=' and prev_tok == NAME:
                    kwarg_name = prev_value
                elif tok == OP and value == ',':
                    if buf:
                        message = ''.join(buf)
                        if kwarg_name in func_kwargs_map:
                            messages_kwargs[kwarg_name] = message
                        else:
                            messages.append(message)
                        del buf[:]
                    else:
                        messages.append(None)
                    kwarg_name = None
                    if translator_comments:
                        # We have translator comments, and since we're on a
                        # comma(,) user is allowed to break into a new line
                        # Let's increase the last comment's lineno in order
                        # for the comment to still be a valid one
                        old_lineno, old_comment = translator_comments.pop()
                        translator_comments.append((old_lineno+1, old_comment))
            elif call_stack > 0 and tok == OP and value == ')':
                call_stack -= 1
            elif funcname and call_stack == -1:
                funcname = func_kwargs_map = kwarg_name = None
            elif tok == NAME and value in keywords:
                funcname = value
                func_kwargs_map = kwargs_maps.get(funcname, {})
                kwarg_name = None


    def extract_javascript_script(fileobj, keywords, comment_tags, options):
        """Extract messages from Javascript embedding in <script> tags.

        Select <script type="javascript/text"> tags and delegate to
        `extract_javascript`.
        """
        from genshi.core import Stream
        from genshi.input import XMLParser

        out = StringIO()
        stream = Stream(XMLParser(fileobj))
        stream = stream.select('//script[@type="text/javascript"]')
        stream.render(out=out, encoding='utf-8')
        out.seek(0)
        return extract_javascript(out, keywords, comment_tags, options)


    class generate_messages_js(Command):
        """Generating message javascripts command for use ``setup.py`` scripts.
        """

        description = 'generate message javascript files from binary MO files'
        user_options = [
            ('domain=', 'D',
             "domain of PO file (default 'messages')"),
            ('input-dir=', 'I',
             'path to base directory containing the catalogs'),
            ('input-file=', 'i',
             'name of the input file'),
            ('output-dir=', 'O',
             "name of the output directory"),
            ('output-file=', 'o',
             "name of the output file (default "
             "'<output_dir>/<locale>.js')"),
            ('locale=', 'l',
             'locale of the catalog to compile'),
        ]

        def initialize_options(self):
            self.domain = 'messages'
            self.input_dir = None
            self.input_file = None
            self.output_dir = None
            self.output_file = None
            self.locale = None

        def finalize_options(self):
            if not self.input_file and not self.input_dir:
                raise DistutilsOptionError('you must specify either the input '
                                           'file or directory')
            if not self.output_file and not self.output_dir:
                raise DistutilsOptionError('you must specify either the '
                                           'output file or directory')

        def run(self):
            mo_files = []
            js_files = []

            def js_path(dir, locale):
                return os.path.join(dir, locale + '.js')

            if not self.input_file:
                if self.locale:
                    mo_files.append((self.locale,
                                     os.path.join(self.input_dir, self.locale,
                                                  'LC_MESSAGES',
                                                  self.domain + '.mo')))
                    js_files.append(js_path(self.output_dir, self.locale))
                else:
                    for locale in os.listdir(self.input_dir):
                        mo_file = os.path.join(self.input_dir, locale,
                                               'LC_MESSAGES',
                                               self.domain + '.mo')
                        if os.path.exists(mo_file):
                            mo_files.append((locale, mo_file))
                            js_files.append(js_path(self.output_dir, locale))
            else:
                mo_files.append((self.locale, self.input_file))
                if self.output_file:
                    js_files.append(self.output_file)
                else:
                    js_files.append(js_path(self.output_dir, locale))

            if not mo_files:
                raise DistutilsOptionError('no compiled catalogs found')

            if not os.path.isdir(self.output_dir):
                os.mkdir(self.output_dir)

            for idx, (locale, mo_file) in enumerate(mo_files):
                js_file = js_files[idx]
                log.info('generating messages javascript %r to %r',
                         mo_file, js_file)

                with open(mo_file, 'rb') as infile:
                    t = Translations(infile, self.domain)
                    catalog = t._catalog

                with open(js_file, 'w') as outfile:
                    write_js(outfile, catalog, self.domain, locale)


    class check_catalog(Command):
        """Check message catalog command for use ``setup.py`` scripts."""

        description = 'check message catalog files, like `msgfmt --check`'
        user_options = [
            ('domain=', 'D',
             "domain of PO file (default 'messages')"),
            ('input-dir=', 'I',
             'path to base directory containing the catalogs'),
            ('input-file=', 'i',
             'name of the input file'),
            ('locale=', 'l',
             'locale of the catalog to compile'),
        ]

        def initialize_options(self):
            self.domain = 'messages'
            self.input_dir = None
            self.input_file = None
            self.locale = None

        def finalize_options(self):
            if not self.input_file and not self.input_dir:
                raise DistutilsOptionError('you must specify either the input '
                                           'file or directory')

        def run(self):
            for filename in self._get_po_files():
                log.info('checking catalog %s', filename)
                f = open(filename)
                try:
                    catalog = read_po(f, domain=self.domain)
                finally:
                    f.close()
                for message in catalog:
                    for error in self._check_message(catalog, message):
                        log.warn('%s:%d: %s', filename, message.lineno, error)

        def _get_po_files(self):
            if self.input_file:
                return [self.input_file]

            if self.locale:
                return [os.path.join(self.input_dir, self.locale,
                                     'LC_MESSAGES', self.domain + '.po')]

            files = []
            for locale in os.listdir(self.input_dir):
                filename = os.path.join(self.input_dir, locale, 'LC_MESSAGES',
                                        self.domain + '.po')
                if os.path.exists(filename):
                    files.append(filename)
            return sorted(files)

        def _check_message(self, catalog, message):
            errors = [e for e in message.check(catalog)]
            try:
                check_genshi_markup(catalog, message)
            except TranslationError, e:
                errors.append(e)
            return errors


    def check_genshi_markup(catalog, message):
        """Verify the genshi markups in the translation."""
        msgids = message.id
        if not isinstance(msgids, (list, tuple)):
            msgids = (msgids,)
        msgstrs = message.string
        if not isinstance(msgstrs, (list, tuple)):
            msgstrs = (msgstrs,)

        # check using genshi-markup
        if not _GENSHI_MARKUP_SEARCH(msgids[0]):
            return

        for msgid, msgstr in izip(msgids, msgstrs):
            if msgstr:
                _validate_genshi_markup(msgid, msgstr)


    def _validate_genshi_markup(markup, alternative):
        indices_markup = _parse_genshi_markup(markup)
        indices_alternative = _parse_genshi_markup(alternative)
        indices = indices_markup - indices_alternative
        if indices:
            raise TranslationError(
                'genshi markups are unbalanced %s' % \
                ' '.join(['[%d:]' % idx for idx in indices]))


    def _parse_genshi_markup(message):
        from genshi.filters.i18n import parse_msg
        try:
            return set([idx for idx, text in parse_msg(message)
                            if idx > 0])
        except Exception, e:
            raise TranslationError('cannot parse message (%s: %s)' % \
                                   (e.__class__.__name__, unicode(e)))


    def write_js(fileobj, catalog, domain, locale):
        from trac.util.presentation import to_json
        data = {'domain': domain, 'locale': locale}

        messages = {}
        for msgid, msgstr in catalog.iteritems():
            if isinstance(msgid, (list, tuple)):
                messages.setdefault(msgid[0], {})
                messages[msgid[0]][msgid[1]] = msgstr
            elif msgid:
                messages[msgid] = msgstr
            else:
                for line in msgstr.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if ':' not in line:
                        continue
                    name, val = line.split(':', 1)
                    name = name.strip().lower()
                    if name == 'plural-forms':
                        data['plural_expr'] = pluralexpr(val)
                        break
        data['messages'] = messages

        fileobj.write('// Generated messages javascript file '
                      'from compiled MO file\n')
        fileobj.write('babel.Translations.load(')
        fileobj.write(to_json(data).encode('utf-8'))
        fileobj.write(').install();\n')

    def pluralexpr(forms):
        match = re.search(r'\bplural\s*=\s*([^;]+)', forms)
        if not match:
            raise ValueError('Failed to parse plural_forms %r' % (forms,))
        return match.group(1)


    def get_command_overriders():
        # 'bdist_wininst' runs a 'build', so make the latter
        # run a 'compile_catalog' before 'build_py'
        class build(_build):
            sub_commands = [('compile_catalog', None)] + _build.sub_commands

        # 'bdist_egg' isn't that nice, all it does is an 'install_lib'
        class install_lib(_install_lib): # playing setuptools' own tricks ;-)
            def l10n_run(self):
                self.run_command('compile_catalog')
            def run(self):
                self.l10n_run()
                # When bdist_egg is called on distribute 0.6.29 and later, the
                # egg file includes no *.mo and *.js files which are generated
                # in l10n_run() method.
                # We remove build_py.data_files property to re-compute in order
                # to avoid the issue (#11640).
                build_py = self.get_finalized_command('build_py')
                if 'data_files' in build_py.__dict__ and \
                   not any(any(name.endswith('.mo') for name in filenames)
                           for pkg, src_dir, build_dir, filenames
                           in build_py.data_files):
                    del build_py.__dict__['data_files']
                _install_lib.run(self)
        return build, install_lib

    def get_l10n_cmdclass():
        build, install_lib = get_command_overriders()
        return {
            'build': build, 'install_lib': install_lib,
            'check_catalog': check_catalog,
        }

    def get_l10n_js_cmdclass():
        build, _install_lib = get_command_overriders()
        build.sub_commands.insert(0, ('generate_messages_js', None))
        build.sub_commands.insert(0, ('compile_catalog_js', None))
        class install_lib(_install_lib):
            def l10n_run(self):
                self.run_command('compile_catalog_js')
                self.run_command('generate_messages_js')
                self.run_command('compile_catalog')
        return {
            'build': build, 'install_lib': install_lib,
            'check_catalog': check_catalog,
            'extract_messages_js': extract_messages,
            'init_catalog_js': init_catalog,
            'compile_catalog_js': compile_catalog,
            'update_catalog_js': update_catalog,
            'generate_messages_js': generate_messages_js,
            'check_catalog_js': check_catalog,
        }

    def get_l10n_trac_cmdclass():
        build, _install_lib = get_command_overriders()
        build.sub_commands.insert(0, ('generate_messages_js', None))
        build.sub_commands.insert(0, ('compile_catalog_js', None))
        build.sub_commands.insert(0, ('compile_catalog_tracini', None))
        class install_lib(_install_lib):
            def l10n_run(self):
                self.run_command('compile_catalog_tracini')
                self.run_command('compile_catalog_js')
                self.run_command('generate_messages_js')
                self.run_command('compile_catalog')
        return {
            'build': build, 'install_lib': install_lib,
            'check_catalog': check_catalog,
            'extract_messages_js': extract_messages,
            'init_catalog_js': init_catalog,
            'compile_catalog_js': compile_catalog,
            'update_catalog_js': update_catalog,
            'generate_messages_js': generate_messages_js,
            'check_catalog_js': check_catalog,
            'extract_messages_tracini': extract_messages,
            'init_catalog_tracini': init_catalog,
            'compile_catalog_tracini': compile_catalog,
            'update_catalog_tracini': update_catalog,
            'check_catalog_tracini': check_catalog,
        }


except ImportError:
    def get_l10n_cmdclass():
        return
    def get_l10n_js_cmdclass():
        return
    def get_l10n_trac_cmdclass():
        return
