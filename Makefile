#          Makefile for testing Trac (see doc/dev/testing.rst)
#
#          Some i18n tasks are also supported, see HELP below.
# ----------------------------------------------------------------------------
#
# Note that this is a GNU Makefile.
# nmake and other abominations are not supported.
#
# ----------------------------------------------------------------------------

define HELP

 Please use `make <target>' where <target> is one of: 

  clean               delete all compiled python files 
  status              show which Python is used and other infos

  [python=...]        variable for selecting Python version

 ---------------- Testing tasks

  unit-test           run unit tests
  functional-test     run functional tests
  test                run all tests
  coverage            run all tests, under figleaf

  [db=...]            variable for selecting database backend
  [test=...]          variable for selecting a single test file

 ---------------- Standalone test server

  server              start tracd

  [port=...]          variable for selecting the port
  [auth=...]          variable for specifying authentication
  [env=...]           variable for the trac environment or parent dir
  [tracdopts=...]     variable containing extra options

 ---------------- L10N tasks

  extraction          regenerate the messages.pot template file

  update              update all the messages.po file(s)
  update-xy           update the catalog for the xy locale only

  compile             compile all the messages.po files
  compile-xy          compile the catalog for the xy locale only

  check               verify all the messages.po files
  check-xy            verify the catalog for the xy locale only

  stats               translation statistics for all catalogs
  stats-pot           statistics for the messages.pot template file
  stats-xy            statistics for the xy locale only

  [locale=...]        variable for selecting a set of locales

endef
export HELP

# ` (keep emacs font-lock happy)

# ----------------------------------------------------------------------------
#
# Main targets

.PHONY: all help status clean clean-bytecode

ifdef test
all: status
	python $(test)
else
all: help
endif

help:
	@echo "$$HELP"

status:
	@echo -n "Python version: "
	@python -V
	@echo -n "figleaf: "
	@-which figleaf 2>/dev/null || echo 
	@echo "PYTHONPATH=$$PYTHONPATH"
	@echo "TRAC_TEST_DB_URI=$$TRAC_TEST_DB_URI"
	@echo "server-options=$(server-options)"

Trac.egg-info: status
	python setup.py egg_info

clean: clean-bytecode clean-coverage

clean-bytecode:
	find -name \*.py[co] -exec rm {} \;

Makefile Makefile.cfg: ;

# ----------------------------------------------------------------------------
#
# Copy Makefile.cfg.sample to Makefile.cfg and adapt to your local environment,
# no customizations to the present Makefile should be necessary.
#
#
-include Makefile.cfg
#
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
#
# L10N related tasks

ifdef locale
    locales = $(locale)
else
    locales = $(wildcard trac/locale/*/LC_MESSAGES/messages.po)
    locales := $(subst trac/locale/,,$(locales))
    locales := $(subst /LC_MESSAGES/messages.po,,$(locales))
endif

.PHONY: extract extraction update compile check stats

extract extraction:
	python setup.py extract_messages

update-%:
	python setup.py update_catalog -l $(@:update-%=%)

ifdef locale
update: $(addprefix update-,$(locale))
else
update:
	python setup.py update_catalog
endif

compile-%:
	python setup.py compile_catalog -l $(@:compile-%=%)

ifdef locale
compile: $(addprefix compile-,$(locale))
else
compile:
	python setup.py compile_catalog
endif

check: pre-check $(addprefix check-,$(locales))
	@echo "All catalogs checked are OK"

pre-check:
	@echo "checking catalogs for $(locales)..."

check-%:
	@echo -n "$(@): "
	@msgfmt --check trac/locale/$(@:check-%=%)/LC_MESSAGES/messages.po && \
	    echo OK

stats: pre-stats $(addprefix stats-,$(locales))

pre-stats: stats-pot
	@echo "translation statistics for $(locales)..."

stats-pot:
	@echo "translation statistics for messages.pot: "
	@echo -n "$(@): "
	@msgfmt --statistics trac/locale/messages.pot

stats-%:
	@echo -n "$(@): "
	@msgfmt --statistics trac/locale/$(@:stats-%=%)/LC_MESSAGES/messages.po

# ----------------------------------------------------------------------------
#
# Testing related tasks

.PHONY: test unit-test functional-test

test: unit-test functional-test

unit-test: Trac.egg-info
	python ./trac/test.py --skip-functional-tests

functional-test: Trac.egg-info
	python trac/tests/functional/__init__.py -v


# ----------------------------------------------------------------------------
#
# Coverage related tasks

.PHONY: coverage clean-coverage show-coverage

coverage: clean-coverage test-figleaf figleaf/index.html

clean-coverage:
	rm -f .figleaf* *.figleaf
	rm -fr figleaf

show-coverage: figleaf/index.html

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

port ?= 8000
tracdopts ?= -r

define server-options
 $(if $(port),-p $(port))\
 $(if $(auth),-a '$(auth)')\
 $(tracdopts)\
 $(if $(wildcard $(env)/VERSION),$(env),-e $(env))
endef

server: Trac.egg-info
ifdef env
	python trac/web/standalone.py $(server-options)
else
	@echo "\`env' variable was not specified. See \`make help'."
endif

# ----------------------------------------------------------------------------
#
# Setup environment variables

python-home := $(python.$(if $(python),$(python),$($(db).python)))
ifndef python-home
    python-home = $(subst /bin,,$(dir $(shell which python)))
endif

ifeq "$(OS)" "Windows_NT"
    SEP = ;
    python-bin = $(python-home):$(python-home)/Scripts
else
    SEP = :
    python-bin = $(python-home)/bin
endif

export TRAC_TEST_DB_URI = $($(db).uri)
export PATH := $(python-bin):$(PATH)
export PYTHONPATH := .$(SEP)$(PYTHONPATH)
# ----------------------------------------------------------------------------
