# == Makefile for Trac related tasks
#
# Automating testing, l10n tasks, documentation generation, ... see HELP below
# ----------------------------------------------------------------------------
#
# Note about customization:
#
#   No changes to the present Makefile should be necessary,
#   configuration should take place in the Makefile.cfg file.
#
#   Copy Makefile.cfg.sample to Makefile.cfg and adapt it
#   to match your local environment.
#
# Note that this is a GNU Makefile, nmake and other abominations are
# not supported. On Windows, you can use it from a msys2 shell, like
# the one that comes part of https://git-for-windows.github.io.
#
# ============================================================================

define HELP

 The Trac Makefile is here to help automate development and
 maintenance tasks.

 Please use `make <target>' where <target> is one of:

  clean               delete all compiled files
  status              show which Python is used and other infos

  [python=...]        variable for selecting Python version
  [pythonopts=...]    variable containing extra options for the interpreter

 As there are many more tasks available, you can ask for specific help:

  help-code           tasks for checking the code style
  help-testing        tasks and configuration parameters for testing
  help-server         tasks and configuration for starting tracd
  help-l10n           tasks and configuration for L10N maintenance
  help-doc            tasks and configuration for preparing Trac documentation
  help-release        tasks and configuration for preparing a Trac release
  help-misc           several other tasks

  help-all            all the tasks at a glance...
endef
# `
export HELP

define HELP_CFG
 It looks like you don't have a Makefile.cfg file yet.
 You can get started by doing `cp Makefile.cfg.sample Makefile.cfg'
 and then adapt it to your environment.
endef
export HELP_CFG

# ============================================================================

# ----------------------------------------------------------------------------
#
# Main targets
#
# ----------------------------------------------------------------------------

.PHONY: all help help-all status clean clean-bytecode clean-mo

%.py : status
	$(PYTHON) -m unittest $(testopts) $(subst /,.,$(@:.py=)).test_suite

ifdef test
all: status
	$(PYTHON) -m unittest $(testopts) $(subst /,.,$(test:.py=)).test_suite
else
all: help
endif

help: Makefile.cfg
	@echo "$$HELP"

help_variables = $(filter HELP_%,$(.VARIABLES))
help_targets = $(filter-out help-CFG,$(help_variables:HELP_%=help-%))

.SECONDEXPANSION:
help-all: $$(sort $$(help_targets))


help-%: Makefile.cfg
	@echo "$${HELP_$*}"

Makefile.cfg:
	@echo "$$HELP_CFG"

status:
	@echo
	@echo "Python: $$(which $(PYTHON)) $(pythonopts)"
	@echo
	@$(PYTHON) contrib/make_status.py
	@echo
	@echo "Variables:"
	@echo "  PATH=$$PATH"
	@echo "  PYTHONPATH=$$PYTHONPATH"
	@echo "  TRAC_TEST_DB_URI=$$TRAC_TEST_DB_URI"
	@echo "  server-options=$(server-options)"
	@echo
	@echo "External dependencies:"
	@printf "  Git version: "
	@git --version 2>/dev/null || echo "not installed"
	@printf "  Subversion version: "
	@svn --version -q 2>/dev/null || echo "not installed"
	@echo

Trac.egg-info: status
	$(PYTHON) setup.py egg_info

clean: clean-bytecode clean-coverage clean-doc

clean-bytecode:
	find . -name \*.py[co] -exec rm {} \;

Makefile: ;

# ----------------------------------------------------------------------------
#
# Copy Makefile.cfg.sample to Makefile.cfg and adapt to your local
# environment, no customization of the present Makefile should be
# necessary.
#
#
-include Makefile.cfg
#
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
#
# L10N related tasks
#
# ----------------------------------------------------------------------------

define HELP_l10n

 ---------------- L10N tasks

  init-xy             create catalogs for given xy locale

  extraction          regenerate the catalog templates

  update              update all the catalog files from the templates
  update-xy           update the catalogs for the xy locale only
  [updateopts=...]    variable containing extra options for update (e.g. -N)

  compile             compile all the catalog files
  compile-xy          compile the catalogs for the xy locale only

  check               verify all the catalog files
  check-xy            verify the catalogs for the xy locale only

  stats               detailed translation statistics for all catalogs
  stats-pot           total messages in the catalog templates
  stats-xy            translated, fuzzy, untranslated for the xy locale only

  summary             display percent translated for all catalogs
  summary-xy          display percent translated for the xy locale only
                      (suitable for a commit message)

  tx-merge            merge catalogs from Transifex for all locales
  tx-merge-xy         merge catalogs from Transifex for the xy locale only

  xdiff               show changes to message strings for all catalogs
  xdiff-pot           show changes to message strings in the catalog template
  xdiff-xy            show changes to message strings for the xy locale

  diff                show summarized changes after an update for all catalogs
  diff-xy             show summarized changes after an update for the xy locale
  [vc=...]            variable containing the version control command to use

  [locale=...]        variable for selecting a set of locales

endef
export HELP_l10n

catalogs = messages messages-js tracini

ifdef locale
    locales = $(locale)
else
    locales = $(wildcard trac/locale/*/LC_MESSAGES/messages.po)
    locales := $(subst trac/locale/,,$(locales))
    locales := $(subst /LC_MESSAGES/messages.po,,$(locales))
    locales := $(sort $(locales))
endif

# Note: variables only valid within a $(foreach catalog,...) evaluation
catalog.po = trac/locale/$(*)/LC_MESSAGES/$(catalog).po
catalog.pot = trac/locale/$(catalog).pot
catalog_stripped = $(subst messages,,$(subst -,,$(catalog)))
_catalog = $(if $(catalog_stripped),_)$(catalog_stripped)

.PHONY: extract extraction update compile check stats summary diff


init-%:
	@$(foreach catalog,$(catalogs), \
	    [ -e $(catalog.po) ] \
	    && echo "$(catalog.po) already exists" \
	    || $(PYTHON) setup.py init_catalog$(_catalog) -l $(*);)


extract extraction:
	$(PYTHON) setup.py $(foreach catalog,$(catalogs),\
	    extract_messages$(_catalog))


update-%:
	$(PYTHON) setup.py $(foreach catalog,$(catalogs), \
	    update_catalog$(_catalog) -l $(*)) $(updateopts)

ifdef locale
update: $(addprefix update-,$(locale))
else
update:
	$(PYTHON) setup.py $(foreach catalog,$(catalogs), \
	    update_catalog$(_catalog)) $(updateopts)
endif


compile-%:
	$(PYTHON) setup.py $(foreach catalog,$(catalogs), \
	    compile_catalog$(_catalog) -l $(*)) \
	    generate_messages_js -l $(*)

ifdef locale
compile: $(addprefix compile-,$(locale))
else
compile:
	$(PYTHON) setup.py $(foreach catalog,$(catalogs), \
	    compile_catalog$(_catalog)) generate_messages_js
endif


check: pre-check $(addprefix check-,$(locales))
	@echo "All catalogs checked are OK"

pre-check:
	@echo "checking catalogs for $(locales)..."

check-%:
	@printf "$(@): "
	$(PYTHON) setup.py $(foreach catalog,$(catalogs), \
	    check_catalog$(_catalog) -l $(*))
	@$(foreach catalog,$(catalogs), \
	    msgfmt --check $(catalog.po) &&) echo msgfmt OK
	@rm -f messages.mo


stats: pre-stats $(addprefix stats-,$(locales))

pre-stats: stats-pot
	@echo "translation statistics for $(locales)..."

stats-pot:
	@echo "translation statistics for catalog templates:"
	@$(foreach catalog,$(catalogs), \
	    printf "$(catalog.pot): "; \
	    msgfmt --statistics $(catalog.pot);)
	@rm -f messages.mo

stats-%:
	@$(foreach catalog,$(catalogs), \
	    [ -e $(catalog.po) ] \
	    && { printf "$(catalog.po): "; \
	         msgfmt --statistics $(catalog.po); } \
	    || echo "$(catalog.po) doesn't exist (make init-$(*))";)
	@rm -f messages.mo


summary: $(addprefix summary-,$(locales))

define untranslated-sh
LC_ALL=C msgfmt --statistics $(catalog.pot) 2>&1 \
  | tail -1 \
  | sed -e 's/0 translated messages, \([0-9]*\) un.*/\1/'
endef

define translated-sh
{ LC_ALL=C msgfmt --statistics $(catalog.po) 2>&1 || echo 0; } \
    | tail -1 \
    | sed -e 's/[^0-9]*\([0-9]*\) translated.*/\1/'
endef

MESSAGES_TOTAL = \
    $(eval MESSAGES_TOTAL := ($(foreach catalog,$(catalogs), \
                                  $(shell $(untranslated-sh)) + ) 0)) \
    $(MESSAGES_TOTAL)

summary-%:
	@$(PYTHON) -c "print('l10n/$(*): translations updated (%d%%)' \
	    % (($(foreach catalog,$(catalogs), \
	          $(shell $(translated-sh)) + ) 0) * 100.0 \
	       / $(MESSAGES_TOTAL)))"
	@rm -f messages.mo


tx-merge-%:
	@$(foreach catalog,$(catalogs), \
	    touch $(catalog.po); \
	    mv $(catalog.po) $(catalog.po).orig; \
	)
	@tx pull --force --no-interactive -l $(*)
	@$(foreach catalog,$(catalogs), \
	    [ -f $(catalog.po) ] && mv $(catalog.po) $(catalog.po).tx; \
	    mv $(catalog.po).orig $(catalog.po); \
	    [ -f $(catalog.po).tx ] && { \
	        $(PYTHON) contrib/merge_catalog.py $(catalog) $(catalog.po).tx $(*); \
	        rm $(catalog.po).tx; \
	    }; \
	)

tx-merge: $(addprefix tx-merge-,$(filter-out en_US,$(locales)))


diff: $(addprefix diff-,$(locales))

ifndef vc
ifneq "$(wildcard $(CURDIR)/.svn)" ""
    vc := svn
else ifneq "$(wildcard $(CURDIR)/.git)" ""
    vc := git
else ifneq "$(wildcard $(CURDIR)/.hg)" ""
    vc := hg
endif
endif

define vc_cat-svn
    $(vc) cat -rBASE $(1)
endef
define vc_cat-git
    $(vc) show HEAD:$(1)
endef
define vc_cat-hg
    $(vc) cat -r. $(1)
endef
define vc_cat
    $(call vc_cat-$(vc),$(1))
endef

define xdiff_catalog
    { \
        $(call vc_cat,$(1)) \
            | msgcat --no-wrap --no-location -s -i - >$(1).tmp; \
        msgcat --no-wrap --no-location -s -i - <$(1) \
            | diff -u -L $(1) -L $(1) $(1).tmp - || :; \
        rm -- $(1).tmp; \
    }
endef


xdiff-pot:
	@$(foreach catalog,$(catalogs), \
	    $(call xdiff_catalog,$(catalog.pot)); \
	)

xdiff-%:
	@$(foreach catalog,$(catalogs), \
	    $(call xdiff_catalog,$(catalog.po)); \
	)

xdiff: $(addprefix xdiff-,$(locales))

diff-%:
	@diff=l10n-$(*).diff; \
	$(vc) diff trac/locale/$(*) > $$diff; \
	[ -s $$diff ] && { \
	    printf "# $(*) changed -> "; \
	    $(PYTHON) contrib/l10n_diff_index.py $$diff; \
	} || rm $$diff

# The above creates l10n-xy.diff files but also a l10n-xy.diff.index
# file pointing to "interesting" diffs (message changes or addition
# for valid msgid).
#
# See also contrib/l10n_sanitize_diffs.py, which removes in-file
# *conflicts* for line change only.

clean-mo:
	find trac/locale -name \*.mo -exec rm {} \;
	find trac/htdocs/js/messages -name \*.js -exec rm {} \;


# ----------------------------------------------------------------------------
#
# Code checking tasks
#
# ----------------------------------------------------------------------------

define HELP_code

 ---------------- Code checking tasks

  pylint              check code with pylint
  jinja               check Jinja2 templates
  coffee              compile .coffee script files into .js files

  [module=...]        module or package to check with pylint
  [templates=...]     list of Jinja2 templates to check
  [coffeescripts=...] list of coffee script files to compile

endef
export HELP_code

.PHONY: pylint jinja coffee

pylintopts = --persistent=n --init-import=y \
--disable=E0102,E0211,E0213,E0602,E0611,E1002,E1101,E1102,E1103 \
--disable=F0401 \
--disable=W0102,W0141,W0142,W0201,W0212,W0221,W0223,W0231,W0232, \
--disable=W0401,W0511,W0603,W0613,W0614,W0621,W0622,W0703 \
--disable=C0103,C0111 \

ifdef module
pylint:
	pylint $(pylintopts) $(subst /,.,$(module:.py=))
else
pylint:
	pylint $(pylintopts) trac tracopt
endif


templates ?= $(shell \
    find $$(find trac tracopt -type d -a -name templates) \
        -mindepth 1 -maxdepth 1 -type f | \
    grep -v "~" | grep -v README )

jinja:
	$(PYTHON) contrib/jinjachecker.py $(jinjaopts) $(templates)

coffeescripts ?= $(shell find trac tracopt -name \*.coffee)
coffeescript_major_version ?= \
    $(shell coffee -v 2> /dev/null | \
        sed -E s'/CoffeeScript version ([0-9]+)\.[0-9]+\.[0-9]+/\1/')

coffee:
ifneq "$(coffeescript_major_version)" "1"
	$(error "CoffeeScript version 1.x is required")
endif
	coffee -c $(coffeescripts)


# ----------------------------------------------------------------------------
#
# Testing related tasks
#
# ----------------------------------------------------------------------------

define HELP_testing

 ---------------- Testing tasks

  unit-test           run unit tests
  functional-test     run functional tests
  test-wiki           shortcut for running all wiki unit tests
  test                run all tests
  coverage            run all tests, under coverage

  [db=...]            variable for selecting database backend
  [test=...]          variable for selecting a single test file
  [testopts=...]      variable containing extra options for running tests
  [coverageopts=...]  variable containing extra options for coverage

endef
export HELP_testing

.PHONY: test unit-test functional-test test-wiki

test: unit-test functional-test

unit-test: Trac.egg-info
	SKIP_FUNCTIONAL_TESTS=1 $(PYTHON) -m unittest $(testopts) trac.test.test_suite

functional-test: Trac.egg-info
	$(PYTHON) -m unittest $(testopts) trac.tests.functional.test_suite

test-wiki:
	$(PYTHON) -m unittest $(testopts) trac.tests.allwiki.test_suite

# ----------------------------------------------------------------------------
#
# Coverage related tasks
#
# (see http://nedbatchelder.com/code/coverage/)
#
# ----------------------------------------------------------------------------

COVERAGEOPTS ?= --branch --source=trac,tracopt

.PHONY: coverage clean-coverage show-coverage

coverage: clean-coverage test-coverage show-coverage

clean-coverage:
	coverage erase
	@rm -fr htmlcov

ifdef test
test-coverage:
	coverage run $(test) $(testopts)
else
test-coverage: unit-test-coverage functional-test-coverage
endif

unit-test-coverage:
	coverage run -a $(coverageopts) $(COVERAGEOPTS) \
	    trac/test.py --skip-functional-tests $(testopts)

functional-test-coverage:
	FIGLEAF='coverage run -a $(coverageopts) $(COVERAGEOPTS)' \
	$(PYTHON) trac/tests/functional/__init__.py -v $(testopts)

show-coverage: htmlcov/index.html
	$(if $(START),$(START) $(<))

htmlcov/index.html:
	coverage html --omit=*/__init__.py


# ----------------------------------------------------------------------------
#
# Tracd related tasks
#
# ----------------------------------------------------------------------------

define HELP_server

 ---------------- Standalone test server

  [start-]server      start tracd

  [port=...]          variable for selecting the port
  [auth=...]          variable for specifying authentication
  [env=...]           variable for the trac environment or parent dir
  [tracdopts=...]     variable containing extra options for tracd

endef
export HELP_server

port ?= 8000
tracdopts ?= -r

define server-options
 $(if $(port),-p $(port))\
 $(if $(auth),-a '$(auth)')\
 $(tracdopts)\
 $(if $(wildcard $(env)/VERSION),$(env),-e $(env))
endef

.PHONY: server start-server tracd start-tracd

server tracd start-tracd: start-server

start-server: Trac.egg-info
ifdef env
	$(PYTHON) trac/web/standalone.py $(server-options)
else
	@echo "\`env' variable was not specified. See \`make help'."
endif



# ----------------------------------------------------------------------------
#
# Miscellaneous tasks
#
# ----------------------------------------------------------------------------

define HELP_misc
 ---------------- Miscellaneous

  start-admin         start trac-admin (on `env')
  start-python        start the Python interpreter

  [adminopts=...]     variable containing extra options for trac-admin

endef
# ` (keep emacs font-lock happy)
export HELP_misc


.PHONY: trac-admin start-admin

trac-admin: start-admin

start-admin:
ifneq "$(wildcard $(env)/VERSION)" ""
	@$(PYTHON) trac/admin/console.py $(env) $(adminopts)
else
	@echo "\`env' variable was not specified or doesn't point to one env."
endif


.PHONY: start-python

start-python:
	@$(PYTHON)
# (this doesn't seem to be much, but we're taking benefit of the
# environment setup we're doing below)


# ----------------------------------------------------------------------------
#
# Documentation related tasks
#
# ----------------------------------------------------------------------------

define HELP_doc

 ---------------- Documentation tasks

  apidoc|sphinx       generate the Sphinx documentation (all specified formats)
  apidoc-html         generate the Sphinx documentation in HTML format
  apidoc-pdf          generate the Sphinx documentation in PDF format
  apidoc-check        check for missing symbols in Sphinx documentation
  apidoc-coverage     generate coverage information for Sphinx documentation

  apiref|epydoc       generate the full API reference using Epydoc

  [sphinxformat=...]  list of formats for generated documentation
  [sphinxopts=...]    variable containing extra options for Sphinx
  [sphinxopts-html=...] variable containing extra options used for html format
  [epydocopts=...]    variable containing extra options for Epydoc
  [dotpath=/.../dot]  path to Graphviz dot program (not used yet)
endef
export HELP_doc

.PHONY: apidoc sphinx apidoc-check apiref epydoc clean-doc

# We also try to honor the "conventional" environment variables used by Sphinx
sphinxopts ?= $(SPHINXOPTS)
SPHINXBUILD ?= sphinx-build
BUILDDIR ?= build/doc
PAPER ?= a4
sphinxopts-latex ?= -D latex_paper_size=$(PAPER)
sphinxformat = html

sphinx: apidoc
apidoc: $(addprefix apidoc-,$(sphinxformat))

apidoc-check:
	@$(PYTHON) doc/utils/checkapidoc.py

apidoc-%:
	@$(SPHINXBUILD) -b $(*) \
	    $(sphinxopts) $(sphinxopts-$(*)) \
	    -d build/doc/doctree \
	    doc $(BUILDDIR)/$(*)
	@$(if $(findstring coverage,$(*)),\
	    diff -u doc/utils/python.txt $(BUILDDIR)/coverage/python.txt)


epydoc: apiref
apiref: doc-images
	@$(PYTHON) doc/utils/runepydoc.py --config=doc/utils/epydoc.conf \
	    $(epydocopts) $(if $(dotpath),--dotpath=$(dotpath))

doc-images: $(addprefix build/,$(wildcard doc/images/*.png))
build/doc/images/%: doc/images/% | build/doc/images
	@cp $(<) $(@)
build/doc/images:
	@mkdir -p $(@)

clean-doc:
	rm -fr build/doc


# ----------------------------------------------------------------------------
#
# Release related tasks
#
# ----------------------------------------------------------------------------

define HELP_release

 ---------------- Release tasks

  release             release-exe on Windows, release-src otherwise
  release-src         generate the .tar.gz and .whl packages
  release-exe         generate the Windows installers (32- and 64-bits)
  release-clean       remove the packages

  update-help         fetches latest help/guide from Edgewall
  update-copyright    update copyright year in file headers
  checksum            MD5 and SHA1 checksums of packages of given version
  upload              scp the packages of given version to user@lynx:~/dist

  [version=...]       version number, mandatory for checksum and upload
  [prefix=...]        wiki page prefix for update-help
endef
export HELP_release

.PHONY: release release-src wheel dist release-exe wininst
.PHONY: release-clean checksum update-copyright update-help upload

ifeq "$(OS)" "Windows_NT"
release: release-exe
else # !Windows_NT
release: release-src
endif # Windows_NT

release-clean:
ifeq "$(version)" ""
	$(error "specify version= on the make command-line")
else
	@rm $(sdist+wheel) $(wininst)
endif

user ?= $(or $(USER),$(LOGNAME),$(USERNAME))
lynx = $(user)@lynx.edgewall.com:/home/$(user)/dist
SCP ?= scp

release-src: wheel sdist

wheel:
	@$(PYTHON) setup.py bdist_wheel
sdist:
	@$(PYTHON) setup.py sdist

sdist+wheel = $(sdist_gztar) $(bdist_wheel)

sdist_gztar = dist/Trac-$(version).tar.gz
bdist_wheel = dist/Trac-$(version)-py2-none-any.whl


ifeq "$(OS)" "Windows_NT"
release-exe:
ifdef python.x86
	make python=x86 wininst
else
	$(error "define python.x86 in Makefile.cfg for building $(wininst.x86)")
endif
ifdef python.x64
	make python=x64 wininst
else
	$(error "define python.x64 in Makefile.cfg for building $(wininst.x64)")
endif

wininst = $(wininst.x86) $(wininst.x64)

wininst.x86 = dist/Trac-$(version).win32.exe
wininst.x64 = dist/Trac-$(version).win-amd64.exe

wininst:
	@$(PYTHON) setup.py bdist_wininst
endif # Windows_NT

packages = $(wildcard $(sdist+wheel) $(wininst))

checksum:
ifeq "$(version)" ""
	$(error "specify version= on the make command-line")
else
	@echo "Packages for Trac-$(version):"
	@echo
	@$(if $(packages), \
	    $(PYTHON) contrib/checksum.py md5:sha256 $(packages) \
	, \
	    echo "No packages found: $(sdist+wheel) $(wininst)" \
	)
endif

copyright_re := "s/^($$PREFIX)(Copyright \(C\) 20[0-9][0-9])(-20[0-9][0-9])?$\
    ( Edgewall Software)$$/\1\2-$(year)\4/g"

update-copyright:
ifeq "$(year)" ""
	$(error "specify year= on the make command-line")
else
	$(eval SED = $(if \
	    $(shell sed --version 2>/dev/null | grep -qF "(GNU sed)" \
	      && echo 1), \
	    sed --in-place= -r -e, \
	    sed -i '' -E))
	@PREFIX="<!--!  "; find . -type f -name "*.html" \
	    -exec $(SED) $(copyright_re) {} \;
	@PREFIX="\# "; find . -type f \
	    \( -name "*.py" -o -name "*.po" -o -name "*.pot" -o \
	       -name "*.ps1" -o -name "*.cgi" -o -name "*.fcgi" \) \
	    -exec $(SED) $(copyright_re) {} \;
	@PREFIX="\# "; $(SED) $(copyright_re) \
	    contrib/trac-svn-hook contrib/trac-pre-commit-hook
	@PREFIX=":: "; $(SED) $(copyright_re) \
	    contrib/trac-svn-post-commit-hook.cmd
	@PREFIX=; $(SED) $(copyright_re) COPYING
	@$(SED) "s/( year *= *)'(20[0-9][0-9])-20[0-9][0-9]'/\1'\2-$(year)'/" \
	    trac/admin/console.py trac/templates/about.html
endif

update-help:
	@$(PYTHON) contrib/checkwiki.py -d --prefix=$(prefix)
	@$(PYTHON) contrib/wiki2rst.py TracUpgrade > UPGRADE.rst
	@$(PYTHON) contrib/wiki2rst.py TracInstall > INSTALL.rst

upload: checksum
ifeq "$(user)" ""
	$(error "define user in Makefile.cfg for uploading to lynx")
else
	$(if $(packages),$(SCP) $(packages) $(lynx))
endif # user



# ============================================================================
#
# Setup environment variables

PYTHON ?= python
PYTHON := $(PYTHON) $(pythonopts)

python-home := $(python.$(or $(python),$($(db).python)))

ifeq "$(findstring ;,$(PATH))" ";"
    SEP = ;
    START ?= start
else
    SEP = :
    START ?= xdg-open
endif

ifeq "$(OS)" "Windows_NT"
    ifndef python-home
        # Detect location of current python
        python-exe := $(shell python -c 'import sys; print(sys.executable)')
        python-home := $(subst \python.exe,,$(python-exe))
        ifeq "$(SEP)" ":"
            python-home := /$(subst :,,$(subst \,/,$(python-home)))
        endif
    endif
    python-bin = $(python-home)$(SEP)$(python-home)/Scripts
endif

define prepend-path
$(if $2,$(if $1,$1$(SEP)$2,$2),$1)
endef

PATH-extension = $(call prepend-path,$(python-bin),$(path.$(python)))
PYTHONPATH-extension = $(call prepend-path,.,$(pythonpath.$(python)))

export PATH := $(call prepend-path,$(PATH-extension),$(PATH))
export PYTHONPATH := $(call prepend-path,$(PYTHONPATH-extension),$(PYTHONPATH))
export TRAC_TEST_DB_URI = $($(db).uri)

# Misc.
space = $(empty) $(empty)
comma = ,
# ----------------------------------------------------------------------------
