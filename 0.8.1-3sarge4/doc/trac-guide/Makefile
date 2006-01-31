DOCFILE_BASE_DEFAULT:=trac-guide
DOCFILE_EXT_DEFAULT:=xml

SVNVERSION = svnversion
BOOK_VERSION_SOURCE =  version.xml

# Standard docfile processing as copied from UFFI
# Placed into public domain by author Kevin Rosenberg

ifndef DOCFILE_BASE
DOCFILE_BASE=${DOCFILE_BASE_DEFAULT}
endif

ifndef DOCFILE_EXT
DOCFILE_EXT=${DOCFILE_EXT_DEFAULT}
endif

DOCFILE:=${DOCFILE_BASE}.${DOCFILE_EXT}
FOFILE:=${DOCFILE_BASE}.fo
PDFFILE:=${DOCFILE_BASE}.pdf
PSFILE:=${DOCFILE_BASE}.ps
DVIFILE:=${DOCFILE_BASE}.dvi
TXTFILE:=${DOCFILE_BASE}.txt
HTMLFILE:=${DOCFILE_BASE}.html
TMPFILES:=${DOCFILE_BASE}.aux ${DOCFILE_BASE}.out ${DOCFILE_BASE}.log
DOCFILES:=$(shell echo *.xml *.xsl)

ifeq ($(XSLTPROC),)
  XSLTPROC:=xsltproc
endif

CATALOG:=`pwd`/catalog-debian.xml
CHECK:=XML_CATALOG_FILES="$(CATALOG)" xmllint --noout --xinclude --postvalid $(DOCFILE) || exit 1

.PHONY: all
all: html 

.PHONY: dist
dist: html pdf

.PHONY: doc
doc: html pdf

.PHONY: check
check:
	@$(CHECK)

.PHONY: html_chunked
html_chunked: html-stamp

html-stamp: $(DOCFILES) Makefile 
	@rm -rf html
	@mkdir html
	@XML_CATALOG_FILES="$(CATALOG)" $(XSLTPROC) --stringparam chunker.output.encoding ISO-8859-1 \
		 --xinclude --output html/ html_chunk.xsl $(DOCFILE)
	touch html-stamp

.PHONY: html
html: ${HTMLFILE}

${HTMLFILE}: $(DOCFILES) Makefile 
	@XML_CATALOG_FILES="$(CATALOG)" $(XSLTPROC) \
		 --xinclude --output ${HTMLFILE} html.xsl $(DOCFILE)

.PHONY: fo
fo: ${FOFILE}

${FOFILE}: $(DOCFILES) Makefile 
	@XML_CATALOG_FILES="$(CATALOG)" $(XSLTPROC) --xinclude --output $(FOFILE) fo.xsl $(DOCFILE)

.PHONY: pdf
pdf: ${PDFFILE}

${PDFFILE}: ${DOCFILES} Makefile
	@$(MAKE) fo
	@fop $(FOFILE) -pdf $(PDFFILE) > /dev/null

.PHONY: dvi
dvi: ${DVIFILE}

.PHONY: ps
ps: ${PSFILE}

${PSFILE}: ${DOCFILES} Makefile
	@$(MAKE) fo
	@fop $(FOFILE) -ps $(PSFILE) > /dev/null


.PHONY: txt
txt: ${TXTFILE}

${TXTFILE}: ${HTMLFILE}
	@XML_CATALOG_FILES="$(CATALOG)" $(XSLTPROC) --xinclude --output ${HTMLFILE} html.xsl $(DOCFILE)
	w3m -dump ${HTMLFILE} > ${TXTFILE}

.PHONY: clean
clean: 
	@rm -f *~ *.bak *.orig \#*\# .\#* texput.log
	@rm -rf html $(PSFILE) $(HTMLFILE) $(PDFFILE) html-stamp
	@rm -f $(TMPFILES) $(FOFILE)
	@rm -f  $(DVIFILE) $(TXTFILE)

.PHONY: distclean
distclean: clean

$(BOOK_VERSION_SOURCE): book-version

book-version:
	@if $(SVNVERSION) . > /dev/null; then \
	echo '<!ENTITY svn.version "Draft Revision '`$(SVNVERSION) .`'">' > $(BOOK_VERSION_SOURCE).tmp; \
	else \
	echo '<!ENTITY svn.version "Draft">' > $(BOOK_VERSION_SOURCE).tmp; \
	fi
	@if cmp -s $(BOOK_VERSION_SOURCE) $(BOOK_VERSION_SOURCE).tmp; then \
	rm $(BOOK_VERSION_SOURCE).tmp; \
	else \
	mv $(BOOK_VERSION_SOURCE).tmp $(BOOK_VERSION_SOURCE); \
	fi
