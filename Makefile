# Makefile for testing Trac (see doc/dev/testing.rst)
# ----------------------------------------------------------------------------

# copy Makefile.cfg.sample to Makefile.cfg and adapt to your local environment.
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


.PHONY: all
ifdef test
all: status
	python $(test)
else
all:
	@echo "make test|unit-test|functional-test|test=... [db=...] [python=...]"
endif

.PHONY: status
status:
	@python -V
	@echo PYTHONPATH=$$PYTHONPATH

.PHONY: clean
clean:
	find -name \*.py[co] | xargs -d"\n" --no-run-if-empty rm -f
	rm -rf .figleaf* html

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

