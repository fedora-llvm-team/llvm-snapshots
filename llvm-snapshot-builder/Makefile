
# It's necessary to set this because some environments don't link sh -> bash.
SHELL := /bin/bash

PACKAGE=$(shell basename $(CURDIR))
TMP=$(CURDIR)/tmp
SPECFILE=$(PACKAGE).spec
YYYYMMDD_TODAY=$(shell date +%Y%m%d)
VERSION=3.0.3~pre$(YYYYMMDD_TODAY)
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
	echo "%yyyymmdd $(YYYYMMDD_TODAY)" >> $(TMP)/$(PACKAGE)/macros.$(PACKAGE)
	echo "Version: $(VERSION)" > $(TMP)/$(PACKAGE)/$(SPECFILE).tmp
	cat $(TMP)/$(PACKAGE)/$(SPECFILE) >> $(TMP)/$(PACKAGE)/$(SPECFILE).tmp
	mv $(TMP)/$(PACKAGE)/$(SPECFILE).tmp $(TMP)/$(PACKAGE)/$(SPECFILE)
	sed -i '/^Version:\s*6\.6\.6/d' $(TMP)/$(PACKAGE)/$(SPECFILE)

.PHONY: rpm
rpm: tarball
	rpmbuild --define '_topdir $(TMP)' -bb $(TMP)/$(PACKAGE)/$(SPECFILE)

.PHONY: srpm
srpm: tarball
	rpmbuild --define '_topdir $(TMP)' -bs $(TMP)/$(PACKAGE)/$(SPECFILE)

.PHONY: packit-srpm
packit-srpm:
	cd $(CURDIR)/.. && packit srpm
