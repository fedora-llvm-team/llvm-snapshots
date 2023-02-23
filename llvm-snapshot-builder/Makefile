
# It's necessary to set this because some environments don't link sh -> bash.
SHELL := /bin/bash

PACKAGE=$(shell basename $(CURDIR))
TMP=$(CURDIR)/tmp
SPECFILE=$(PACKAGE).spec
VERSION=$(shell grep -Po 'Version:\s*\K(.*)' $(SPECFILE))
TARBALL=$(PACKAGE)-$(VERSION).tar.bz2
FILES = README.md \
		$(SPECFILE) \
		macros.$(PACKAGE)

.PHONY: version
version:
	@echo $(VERSION)

.PHONY: tmp
tmp:
	mkdir -p $(TMP)

.PHONY: tarball
tarball: tmp source
	cd $(TMP) && tar cfj SOURCES/$(TARBALL) $(PACKAGE)
	@echo $(TMP)/SOURCES/$(TARBALL)

.PHONY: clean
clean:
	rm -rf $(TMP)
	rm -f $(TARBALL)

.PHONY: source
source:
	mkdir -p $(TMP)/SOURCES
	mkdir -p $(TMP)/$(PACKAGE)
	cp -a $(FILES) $(TMP)/$(PACKAGE)

.PHONY: rpm
rpm: tarball
	rpmbuild --define '_topdir $(TMP)' -bb $(PACKAGE).spec

.PHONY:
srpm: tarball
	rpmbuild --define '_topdir $(TMP)' -bs $(PACKAGE).spec

.PHONY:
packit-srpm:
	cd $(CURDIR)/.. && packit srpm
