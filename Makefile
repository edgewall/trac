# Makefile for testing Trac (see doc/dev/testing.rst)
# ----------------------------------------------------------------------------
#
# Note that this is a GNU Makefile.
# nmake and other abominations are not supported.
#
# ----------------------------------------------------------------------------

.PHONY: all
ifdef test
all: status
	python $(test)
else
all: help
endif

.PHONY: help
help:
	@echo
	@echo "Please use \`make <target>' where <target> is one of:"
	@echo
	@echo "  clean               delete all compiled python files"
	@echo "  status              which Python and which test db used"
	@echo
	@echo "  [python=...]        select Python version"
	@echo 
	@echo "                  Testing tasks"
	@echo 
	@echo "  unit-test           run unit tests"
	@echo "  functional-test     run functional tests"
	@echo "  test                run all tests"
	@echo
	@echo "  [db=...]            database backend to use for tests"
	@echo "  [test=...]          file to test (all if not specified)"
	@echo 
	@echo "                  L10N tasks"
	@echo 
	@echo "  extract             update the messages.pot file"
	@echo "  update              update the messages.po file(s)"
	@echo "  compile             compile the messages.po files"
	@echo 
	@echo "  [locale=..]             operate on this locale only"
	@echo 

.PHONY: status
status:
	@python -V
	@echo PYTHONPATH=$$PYTHONPATH
	@echo TRAC_TEST_DB_URI=$$TRAC_TEST_DB_URI

.PHONY: clean
clean:
	find -name \*.py[co] | xargs -d"\n" --no-run-if-empty rm -f
	rm -rf .figleaf* html

# L10N related tasks

.PHONY: extract update compile

extract:
	python setup.py extract_messages

update:
	python setup.py update_catalog $(if $(locale),-l $(locale))

compile:
	python setup.py compile_catalog $(if $(locale),-l $(locale))

# Testing related tasks

.PHONY: test unit-test functional-test

test: unit-test functional-test

unit-test: Trac.egg-info
	python ./trac/test.py --skip-functional-tests

functional-test: Trac.egg-info
	python trac/tests/functional/__init__.py -v

.PHONY: coverage
coverage: html/index.html

html/index.html: .figleaf.functional .figleaf.unittests
	figleaf2html --exclude-patterns=trac/tests/figleaf-exclude .figleaf.functional .figleaf.unittests

.figleaf.functional: Trac.egg-info
	FIGLEAF=figleaf python trac/tests/functional/__init__.py -v
	mv .figleaf .figleaf.functional

.figleaf.unittests: Trac.egg-info
	rm -f .figleaf .figleaf.unittests
	figleaf ./trac/test.py --skip-functional-tests
	mv .figleaf .figleaf.unittests

Trac.egg-info: status
	python setup.py egg_info

# ----------------------------------------------------------------------------

# Copy Makefile.cfg.sample to Makefile.cfg and adapt to your local environment.

-include Makefile.cfg

# ----------------------------------------------------------------------------
ifeq "$(OS)" "Windows_NT"
    SEP = ;
else
    SEP = :
endif

export TRAC_TEST_DB_URI = $($(db).uri)
export PATH := $(python.$(if $(python),$(python),$($(db).python))):$(PATH)
export PYTHONPATH := .$(SEP)$(PYTHONPATH)
# ----------------------------------------------------------------------------
