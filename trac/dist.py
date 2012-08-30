# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Edgewall Software
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

from StringIO import StringIO
from itertools import izip
import os
import re

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

    _GENSHI_MARKUP_SEARCH = re.compile(r'\[[0-9]+:').search


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

                infile = open(mo_file, 'rb')
                try:
                    t = Translations(infile, self.domain)
                    catalog = t._catalog
                finally:
                    infile.close()

                outfile = open(js_file, 'w')
                try:
                    write_js(outfile, catalog, self.domain, locale)
                finally:
                    outfile.close()


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


except ImportError:
    def get_l10n_cmdclass():
        return
    def get_l10n_js_cmdclass():
        return
