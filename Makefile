.PHONY: all
all:

.PHONY: test
test:
	./trac/test.py -v

.PHONY: coverage
coverage:
	rm -f .figleaf .figleaf.unittests
	figleaf ./trac/test.py -v --skip-functional-tests
	mv .figleaf .figleaf.unittests
	FIGLEAF=figleaf python trac/tests/functional/testcases.py -v
	mv .figleaf .figleaf.functional
	figleaf2html --exclude-patterns=../figleaf-exclude .figleaf.functional .figleaf.unit tests


