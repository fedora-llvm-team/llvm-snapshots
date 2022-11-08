# It's necessary to set this because some environments don't link sh -> bash.
SHELL := /bin/bash

# Current working directory
pwd = $(shell pwd)

today = $(shell date +%Y%m%d)

# YearMonthDay to build for (defaults to today)
yyyymmdd ?= $(today)

# A directory in which we checkout the sources for the package and store the
# build artifacts (e.g. SRPM, RPM)
buildroot ?= $(pwd)/buildroot/$(yyyymmdd)

# The default chroot to build for.
chroot ?= fedora-36-x86_64

# The mock config that will be used as a template for the final mock config.
# In it we will place the chroot defined above.
mockconfig_template = $(pwd)/mock-config.cfg

# The final mock config location used for the actual build. Will be generated
# upon each invokation.
mockconfig = $(buildroot)/mock-config.cfg

# In case we build on copr, this will be the project to use.
copr_project ?= kkleine/llvm-snapshots-incubator-$(yyyymmdd)

# Include the file that provides the "help" and "help-html" targets.
include ./help.mk

# Builds the mock config if it doesn't exist
$(mockconfig): $(mockconfig_template)
	echo "Creating mock config"
	$(shell mkdir -pv $(buildroot))
	$(shell chroot=$(chroot) envsubst $${chroot} < $(mockconfig_template) > $(mockconfig))

## Clones the upstream-snapshot branch of the given package package (%) into the
## buildroot.
clone-%:
	$(eval package:=$(subst clone-,,$@))
	@if [ ! -d "$(buildroot)/$(package)" ]; then \
		fedpkg clone --anonymous -b upstream-snapshot $(package) $(buildroot)/$(package); \
	else \
		echo ""; \
		echo "NOT CLONING BECAUSE DIRECTORY ALREADY EXISTS: $(buildroot)/$(package)"; \
		echo ""; \
	fi

## Clones and builds the package (%) and then installs it in the chroot.
build-%:
	$(eval package:=$(subst build-,,$@))
	$(MAKE) clone-$(package)
	$(MAKE) build-and-install-$(package)

.PHONY: init-mock
## Initializes the mock chroot.
init-mock: $(mockconfig)
	mock -r $(mockconfig) \
		--init \
		--with snapshot_build \

## For the package (%) an SRPM and an RPM is built and then it is installed in
## the chroot.
build-and-install-%: $(mockconfig)
	$(eval package:=$(subst build-and-install-,,$@))
	cd $(buildroot)/$(package) \
	&& mock -r $(mockconfig) \
		--define "_disable_source_fetch 0" \
		--define "yyyymmdd $(yyyymmdd)" \
		--rebuild \
		--no-cleanup \
		--no-cleanup-after \
		--spec $(package).spec \
		--sources $(buildroot)/$(package) \
		--resultdir $(buildroot)/$(package) \
		--postinstall

.PHONY: shell
## Opens up a shell to inspect the mock chroot.
shell: $(mockconfig)
	mock -r $(mockconfig) --shell

.PHONY: install-vim
## Allows you to use vim inside of mock.
install-vim: $(mockconfig)
	mock -r $(mockconfig) --install vim

.PHONY: clean-mock
## Cleans the mock chroot
clean-mock: $(mockconfig)
	mock -r $(mockconfig) clean

.PHONY: clean-buildroot
## Removes the buildroot directory
clean-buildroot:
	rm -rf $(buildroot)

.PHONY: clean
## Cleans the mock chroot and removes the buildroot.
clean: clean-mock clean-buildroot

## Removes the buildroot dir for the given package (%).
clean-%:
	$(eval package:=$(subst clean-,,$@))
	rm -rf $(buildroot)/$(package)

## Builds the package (%) in copr by using the tooling used for the automated
## snapshot generation.
copr-build-%:
	$(eval package:=$(subst copr-build-,,$@))
	@if [ "$(today)" != "$(yyyymmdd)" ]; then \
		echo "Sorry, but due to the project setup in copr we can only build for today ($(today))!"; \
		exit 1; \
	fi
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	python -m llvm_snapshot_builder.cli --verbose \
		create-project \
		--proj "$(copr_project)" \
		--description-file "$(pwd)/project-description.md" \
		--instructions-file "$(pwd)/project-instructions.md" \
		--delete-after-days 7 \
		--chroots $(chroot) \
		--update
	python -m llvm_snapshot_builder.cli --verbose \
		create-packages \
		--proj "$(copr_project)" \
		--packagenames $(package) \
		--update
	python -m llvm_snapshot_builder.cli --verbose \
		build-packages \
		--proj "$(copr_project)" \
		--chroots $(chroot) \
		--packagenames $(package) \
		--timeout "108000" 


