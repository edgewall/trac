# == Makefile for Trac related tasks (beyond those supported by setuptools) ==
#
# Automating testing, i18n tasks, documentation generation, ... see HELP below
# ----------------------------------------------------------------------------
#
# Note about customization:
#   No changes to the present Makefile should be necessary,
#   rather copy Makefile.cfg.sample to Makefile.cfg and adapt it
#   to match your local environment.
#
# Note that this is a GNU Makefile, nmake and other abominations are
# not supported.
#
# ============================================================================

define HELP

 Please use `make <target>' where <target> is one of: 

  clean               delete all compiled files 
  status              show which Python is used and other infos

  [python=...]        variable for selecting Python version

 ---------------- Testing tasks

  unit-test           run unit tests
  functional-test     run functional tests
  test-wiki           shortcut for running all wiki unit tests
  test                run all tests
  coverage            run all tests, under coverage
  figleaf             run all tests, under figleaf

  [db=...]            variable for selecting database backend
  [test=...]          variable for selecting a single test file
  [testopts=...]      variable containing extra options for running tests
  [coverageopts=...]  variable containing extra options for coverage

 ---------------- Standalone test server

  server              start tracd

  [port=...]          variable for selecting the port
  [auth=...]          variable for specifying authentication
  [env=...]           variable for the trac environment or parent dir
  [tracdopts=...]     variable containing extra options for tracd

 ---------------- L10N tasks

  init-xy             create catalogs for given xy locale

  extraction          regenerate the catalog templates

  update              update all the catalog files from the templates
  update-xy           update the catalogs for the xy locale only

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

  diff                show relevant changes after an update for all catalogs
  diff-xy             show relevant changes after an update for the xy locale

  [locale=...]        variable for selecting a set of locales

 ---------------- Documentation tasks

  apidoc|sphinx       generate the Sphinx documentation (all specified formats)
  apidoc-html         generate the Sphinx documentation in HTML format
  apidoc-pdf          generate the Sphinx documentation in PDF format

  apiref|epydoc       generate the full API reference using Epydoc

  [sphinxformat=...]  list of formats for generated documentation
  [sphinxopts=...]    variable containing extra options for Sphinx
  [sphinxopts-html=...] variable containing extra options used for html format
  [epydocopts=...]    variable containing extra options for Epydoc
  [dotpath=/.../dot]  path to Graphviz' dot program (not used yet)
                         
endef
export HELP

# ` (keep emacs font-lock happy)

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

.PHONY: all help status clean clean-bytecode clean-mo

ifdef test
all: status
	python $(test) $(testopts)
else
all: help
endif

help: Makefile.cfg
	@echo "$$HELP"


Makefile.cfg:
	@echo "$$HELP_CFG"

status:
	@echo -n "Python version: "
	@python -V
	@echo -n "figleaf: "
	@-which figleaf 2>/dev/null || echo 
	@echo -n "coverage: "
	@-which coverage 2>/dev/null || echo 
	@echo "PYTHONPATH=$$PYTHONPATH"
	@echo "TRAC_TEST_DB_URI=$$TRAC_TEST_DB_URI"
	@echo "server-options=$(server-options)"

Trac.egg-info: status
	python setup.py egg_info

clean: clean-bytecode clean-figleaf clean-coverage clean-doc

clean-bytecode:
	find -name \*.py[co] -exec rm {} \;

Makefile: ;

# ----------------------------------------------------------------------------
#
-include Makefile.cfg
#
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
#
# L10N related tasks
#
# ----------------------------------------------------------------------------

ifdef locale
    locales = $(locale)
else
    locales = $(wildcard trac/locale/*/LC_MESSAGES/messages.po)
    locales := $(subst trac/locale/,,$(locales))
    locales := $(subst /LC_MESSAGES/messages.po,,$(locales))
    locales := $(sort $(locales))
endif

messages.po = trac/locale/$(*)/LC_MESSAGES/messages.po
messages-js.po = trac/locale/$(*)/LC_MESSAGES/messages-js.po
messages.pot = trac/locale/messages.pot
messages-js.pot = trac/locale/messages-js.pot

.PHONY: extract extraction update compile check stats summary diff

init-%:
	@[ -e $(messages.po) ] \
	 && echo "$(messages.po) already exists" \
	 || python setup.py init_catalog -l $(*)
	@[ -e $(messages-js.po) ] \
	 && echo "$(messages-js.po) already exists" \
	 || python setup.py init_catalog_js -l $(*)

extract extraction:
	python setup.py extract_messages extract_messages_js

update-%:
	python setup.py update_catalog -l $(*) update_catalog_js -l $(*)

ifdef locale
update: $(addprefix update-,$(locale))
else
update:
	python setup.py update_catalog update_catalog_js
endif

compile-%:
	python setup.py compile_catalog -l $(*) \
	    compile_catalog_js -l $(*) generate_messages_js -l $(*)

ifdef locale
compile: $(addprefix compile-,$(locale))
else
compile:
	python setup.py compile_catalog compile_catalog_js
endif

check: pre-check $(addprefix check-,$(locales))
	@echo "All catalogs checked are OK"

pre-check:
	@echo "checking catalogs for $(locales)..."

check-%:
	@echo -n "$(@): "
	@msgfmt --check $(messages.po) && msgfmt --check $(messages-js.po) \
	 && echo OK
	@rm -f messages.mo

stats: pre-stats $(addprefix stats-,$(locales))

pre-stats: stats-pot
	@echo "translation statistics for $(locales)..."

stats-pot:
	@echo "translation statistics for catalog templates:"
	@echo -n "messages.pot: "; msgfmt --statistics $(messages.pot)
	@echo -n "messages-js.pot: "; msgfmt --statistics $(messages-js.pot) 

stats-%:
	@echo -n "messages.po: "; msgfmt --statistics $(messages.po)
	@[ -e $(messages-js.po) ] \
	 && echo -n "messages-js.po: "; msgfmt --statistics $(messages-js.po) \
	 || echo "$(messages-js.po) doesn't exist (make init-$(*))"

summary: $(addprefix summary-,$(locales))

define untranslated-sh
LC_ALL=C msgfmt --statistics $(1) 2>&1 \
  | tail -1 \
  | sed -e 's/0 translated messages, \([0-9]*\) un.*/\1/'
endef

define translated-sh
{ LC_ALL=C msgfmt --statistics $(1) 2>&1 || echo 0; } \
    | tail -1 \
    | sed -e 's/[^0-9]*\([0-9]*\) translated.*/\1/'
endef

MESSAGES_TOTAL = \
    $(eval MESSAGES_TOTAL := ( \
        $(shell $(call untranslated-sh,$(messages.pot))) + \
        $(shell $(call untranslated-sh,$(messages-js.pot)))))\
    $(MESSAGES_TOTAL)

summary-%:
	@python -c "print 'l10n/$(*): translations updated (%d%%)' \
	    % (($(shell $(call translated-sh,$(messages.po))) + \
	        $(shell $(call translated-sh,$(messages-js.po)))) * 100.0 \
	       / $(MESSAGES_TOTAL))"

diff: $(addprefix diff-,$(locales))


diff-%:
	@svn diff trac/locale/$(*) \
	    | grep -Ev '^([-+]#:|[@ ])' | grep -E '^[-+@]' || true

clean-mo:
	find trac/locale -name \*.mo -exec rm {} \;
	find trac/htdocs/js/messages -name \*.js -exec rm {} \;


# ----------------------------------------------------------------------------
#
# Testing related tasks
#
# ----------------------------------------------------------------------------

.PHONY: test unit-test functional-test test-wiki

test: unit-test functional-test

unit-test: Trac.egg-info
	python ./trac/test.py --skip-functional-tests $(testopts)

functional-test: Trac.egg-info
	python trac/tests/functional/__init__.py -v $(testopts)

test-wiki:
	python trac/tests/allwiki.py $(testopts)

# ----------------------------------------------------------------------------
#
# Coverage related tasks
#
# (see http://nedbatchelder.com/code/coverage/)
#
# ----------------------------------------------------------------------------

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
	coverage run -a $(coverageopts) trac/test.py --skip-functional-tests

functional-test-coverage:
	FIGLEAF='coverage run -a $(coverageopts)' python \
	    trac/tests/functional/testcases.py -v

show-coverage: htmlcov/index.html
	#coverage report

htmlcov/index.html:
	coverage html \
	    --omit=$(subst $(space),$(comma),$(wildcard trac/*/templates)),trac/templates

# ----------------------------------------------------------------------------
#
# Figleaf based coverage tasks 
#
# (see http://darcs.idyll.org/~t/projects/figleaf/doc/)
#
# ** NOTE: there are still several issues with this **
#  - as soon as a DocTestSuite is run, figleaf gets confused
#  - functional-test-figleaf is broken (no .figleaf generated)
#
# ----------------------------------------------------------------------------

.PHONY: figleaf clean-figleaf show-figleaf

figleaf: clean-figleaf test-figleaf show-figleaf

clean-figleaf:
	rm -f .figleaf* *.figleaf
	rm -fr figleaf

show-figleaf: figleaf/index.html

figleaf/index.html: $(wildcard *.figleaf)
	figleaf2html \
	    --output-directory=figleaf \
	    --exclude-patterns=trac/tests/figleaf-exclude \
	    *.figleaf


.PHONY: test-figleaf  unit-test-figleaf functional-test-figleaf

test-figleaf: unit-test-figleaf functional-test-figleaf

unit-test-figleaf: unit-test.figleaf

functional-test-figleaf: functional-test.figleaf


functional-test.figleaf: Trac.egg-info
	rm -f .figleaf
	FIGLEAF=figleaf python trac/tests/functional/testcases.py -v
	@mv .figleaf $(@)

unit-test.figleaf: Trac.egg-info
	rm -f .figleaf
	figleaf trac/test.py --skip-functional-tests
	@mv .figleaf $(@)


# ----------------------------------------------------------------------------
#
# Tracd related tasks
#
# ----------------------------------------------------------------------------

port ?= 8000
tracdopts ?= -r

define server-options
 $(if $(port),-p $(port))\
 $(if $(auth),-a '$(auth)')\
 $(tracdopts)\
 $(if $(wildcard $(env)/VERSION),$(env),-e $(env))
endef

.PHONY: server

server: Trac.egg-info
ifdef env
	python trac/web/standalone.py $(server-options)
else
	@echo "\`env' variable was not specified. See \`make help'."
endif


# ----------------------------------------------------------------------------
#
# Documentation related tasks
#
# ----------------------------------------------------------------------------

.PHONY: apidoc sphinx apiref epydoc clean-doc

# We also try to honor the "conventional" environment variables used by Sphinx
sphinxopts ?= $(SPHINXOPTS)
SPHINXBUILD ?= sphinx-build
BUILDDIR ?= build/doc
PAPER ?= a4
sphinxopts-latex ?= -D latex_paper_size=$(PAPER)
sphinxformat = html

sphinx: apidoc
apidoc: $(addprefix apidoc-,$(sphinxformat))

apidoc-%:
	@$(SPHINXBUILD) -b $(*) \
	    $(sphinxopts) $(sphinxopts-$(*)) \
	    -d build/doc/doctree \
	    doc $(BUILDDIR)/$(*)


epydoc: apiref
apiref: doc-images
	@python doc/utils/runepydoc.py --config=doc/utils/epydoc.conf \
	    $(epydocopts) $(if $(dotpath),--dotpath=$(dotpath))

doc-images: $(addprefix build/,$(wildcard doc/images/*.png))
build/doc/images/%: doc/images/% | build/doc/images
	@cp $(<) $(@) 
build/doc/images:
	@mkdir -p $(@)

clean-doc:
	rm -fr build/doc



# ============================================================================
#
# Setup environment variables

python-home := $(python.$(if $(python),$(python),$($(db).python)))

ifeq "$(OS)" "Windows_NT"
    ifndef python-home
        # Detect location of current python 
        python-exe := $(shell python -c 'import sys; print sys.executable')
        python-home := $(subst \python.exe,,$(python-exe))
    endif
    SEP = ;
    python-bin = $(python-home)$(SEP)$(python-home)/Scripts
else
    SEP = :
endif

ifdef python-bin
    export PATH := $(python-bin)$(SEP)$(PATH)
endif
export PYTHONPATH := .$(SEP)$(PYTHONPATH)
export TRAC_TEST_DB_URI = $($(db).uri)

# Misc.
space = $(empty) $(empty)
comma = ,
# ----------------------------------------------------------------------------
