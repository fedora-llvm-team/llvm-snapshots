
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

# .PHONY: lint
# lint:
# 	rpkg lint

# .PHONY: spec
# spec:
# 	rpkg spec --print --spec llvm-snapshot-builder.spec

# .PHONY: local
# local:
# 	mkdir -pv $(shell pwd)/out
# 	rpkg local --outdir=$(shell pwd)/out --spec llvm-snapshot-builder.spec
# 	tree $(shell pwd)/out

# .PHONY: clean
# clean:
# 	rm -rf $(shell pwd)/out

# .PHONY: copr
# copr:
# 	rpkg copr-build \
# 		--spec llvm-snapshot-builder.spec \
# 		@fedora-llvm-team/llvm-snapshot-builder

# .PHONY: reinstall
# reinstall: clean local
# 	sudo dnf -y remove llvm-snapshot-builder
# 	sudo dnf -y install out/noarch/$(shell rpkg nvr)*.rpm

# .PHONY: test
# test: reinstall
# 	rpm --eval "%{llvm_sb}"