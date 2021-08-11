# It's necessary to set this because some environments don't link sh -> bash.
SHELL := /bin/bash

yyyymmdd ?= $(shell date +%Y%m%d)

out = $(shell pwd)/out/$(yyyymmdd)

# When you r, executed commands will be printed before executed
# in the build process.
VERBOSE_FLAG = 
ifeq ($(VERBOSE),1)
       VERBOSE_FLAG = --verbose
endif

# If your user requires sudo to run either docker or podman, try this:
#
#     make CONTAINER_TOOL="sudo podman" <WHATERVER_TARGET>
CONTAINER_TOOL ?= podman
# By default we cache DNF packages because it allows us for avoiding re-download
# problems. To disable DNF caching, do this:
#
#    make CONTAINER_DNF_CACHE= <WHATERVER_TARGET>
CONTAINER_DNF_CACHE ?= -v $(shell pwd)/dnf-cache:/var/cache/dnf:Z
# This exists so that generated files inside the container can be edited from
# the outside as the user running the container.
CONTAINER_PERMS ?= -u $(shell id -u $(USER)):$(shell id -g $(USER))
CONTAINER_INTERACTIVE_SWITCH ?= -i
CONTAINER_RUN_OPTS =  -t --rm $(CONTAINER_INTERACTIVE_SWITCH) $(CONTAINER_PERMS) $(CONTAINER_DNF_CACHE)
CONTAINER_DEPENDENCIES = container-image ./dnf-cache
CONTAINER_IMAGE = kkleine-llvm-snapshot-builder
FEDORA_VERSION ?= 34
KOJI_TAG ?= f$(FEDORA_VERSION)-llvm-snapshot

define build-project-srpm
	$(eval project:=$(1))
	$(eval mounts:=$(2))
	mkdir -pv $(out)/${project}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(out)/${project}:/home/johndoe/rpmbuild:Z \
		$(CONTAINER_IMAGE) $(VERBOSE_FLAG) \
			--reset-project \
			--generate-spec-file \
			--build-srpm \
			--yyyymmdd ${yyyymmdd} \
			--project ${project} \
	|& tee $(out)/build-srpm-${project}.log
endef

define build-project-rpm
	$(eval project:=$(1))
	$(eval mounts:=$(2))
	$(eval enabled_repos:=$(3))
	mkdir -pv $(out)/${project}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(out)/${project}:/home/johndoe/rpmbuild:Z ${mounts} \
		$(CONTAINER_IMAGE) $(VERBOSE_FLAG) \
			--install-build-dependencies \
			--build-rpm \
			--generate-dnf-repo \
			--yyyymmdd ${yyyymmdd} \
			--project ${project} ${enabled_repos} \
	|& tee $(out)/build-rpm-${project}.log
	rm -rf $(out)/${project}/BUILD $(out)/${project}/BUILDROOT
endef

define mount-opts
-v $(out)/$(1)/RPMS:/repo-$(1):Z
endef

define repo-opts
--enable-dnf-repo /repo-$(1)
endef

define get-nvr
	$(eval project:=$(2))
        $(eval nvr:= $(shell basename $(out)/$(project)/SRPMS/*.src.rpm | sed  -s 's/\.src\.rpm$$//' |  sed 's/fc[0-9]\+/fc$(FEDORA_VERSION)/'))
	$(1) := $$(nvr)
endef


mounts_compat_llvm :=
mounts_compat_clang := $(call mount-opts,compat-llvm)
mounts_llvm := 
mounts_python_lit := $(call mount-opts,llvm)
mounts_clang := $(foreach p,python-lit llvm,$(call mount-opts,$(p)))
mounts_lld := $(foreach p,python-lit llvm clang,$(call mount-opts,$(p)))

repos_compat_llvm :=
repos_compat_clang := $(call repo-opts,compat-llvm) 
repos_llvm := 
repos_python_lit := $(call repo-opts,llvm)
repos_clang := $(foreach p,python-lit llvm,$(call repo-opts,$(p)))
repos_lld := $(foreach p,python-lit llvm clang,$(call repo-opts,$(p)))



# TARGETS:


.PHONY: all-srpms
## Build all SRPMS for all of LLVM's sub-projects.
all-srpms: srpm-compat-llvm srpm-compat-clang srpm-llvm srpm-python-lit srpm-clang srpm-lld

.PHONY: srpm-%
## With "make srpm-PROJECT you can build an SRPM for an individual LLVM
## sub-project.
srpm-%: $(CONTAINER_DEPENDENCIES)
	$(eval project:=$(subst srpm-,,$@))
	$(call build-project-srpm,$(project))

.PHONY: all-rpms
## Build all of LLVM's sub-projects in the correct order.
all-rpms: compat-llvm compat-clang llvm python-lit clang lld

.PHONY: clean
## Remove the artifacts for all projects.
clean:
	rm -rf out

.PHONY: clean-%
## "make clean-PROJECT" to remove the artifacts for an
## individual project only.
clean-%:
	$(eval project:=$(subst clean-,,$@))
	rm -rf $(out)/$(project)

.PHONY: clean-cache
## Remove the ./dnf-cache DNF cache directory.
## NOTE: This might require to be run as root for permission problems.
clean-cache:
	rm -rf dnf-cache

./dnf-cache:
	mkdir -p dnf-cache

.PHONY: container-image
## Builds the container image that will be used for build SRPMs and RPMs.
container-image: ./dnf-cache
	$(CONTAINER_TOOL) pull $(shell head -n1 Dockerfile | sed 's/FROM\s\+//')
	$(CONTAINER_TOOL) build --tag $(CONTAINER_IMAGE) .

.PHONY: python-lit
## Build LLVM's python-lit sub-project.
python-lit: $(CONTAINER_DEPENDENCIES)
	$(call build-project-rpm,python-lit)

.PHONY: compat-llvm
## Build the compatibility packages for LLVM's llvm sub-project.
compat-llvm: $(CONTAINER_DEPENDENCIES)
	$(call build-project-rpm,compat-llvm,$(mounts_compat_llvm),$(repos_compat_llvm))

.PHONY: compat-clang
## Build the compatibility packages for LLVM's clang sub-project.
compat-clang: $(CONTAINER_DEPENDENCIES)
	$(call build-project-rpm,compat-clang,$(mounts_compat_clang),$(repos_compat_clang))

.PHONY: llvm
## Build LLVM's llvm sub-project.
llvm: srpm-llvm $(CONTAINER_DEPENDENCIES)
	$(call build-project-rpm,llvm,$(mounts_llvm),$(repos_llvm))

.PHONY: clang
## Build LLVM's clang sub-project.
clang: srpm-clang $(CONTAINER_DEPENDENCIES)
	$(call build-project-rpm,clang,$(mounts_clang),$(repos_clang))

.PHONY: lld
## Build LLVM's lld sub-project.
lld: srpm-lld $(CONTAINER_DEPENDENCIES)
	$(call build-project-rpm,lld,${mounts_lld},$(repos_lld))


# SPECIAL TARGETS:


.PHONY: shell-%
## This mounts a project and with all dependent repos mounted (expecting they
## exist) and then enter a bash-shell for experiments or rerunning tests and
## whatnot. To get the container in a good shape, we also install build
## dependencies as defined in the project's spec file.
shell-%: $(CONTAINER_DEPENDENCIES)
	$(eval project:=$(subst shell-,,$@))
	$(eval project_var:=$(subst -,_,$(project)))
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(out)/$(project):/home/johndoe/rpmbuild:Z $(mounts_$(project_var)) \
		$(CONTAINER_IMAGE) $(VERBOSE_FLAG) \
		    --generate-spec-file \
			--install-build-dependencies \
			--shell \
			--yyyymmdd ${yyyymmdd} \
			--project $(project) $(repos_$(project_var)) \
	|& tee $(out)/shell-$(project).log


.PHONY: koji-compat
## Initiate a koji build of compat-llvm and compat-clang using the
## SRPMs for these packages.
## NOTE: The SRPMs can be generated using "make all-srpms".
koji-compat: koji-compat-llvm \
			 koji-wait-repo-compat-llvm \
			 koji-compat-clang \
			 koji-wait-repo-compat-clang \
			 koji-tag-compat \
			 koji-create-repo

.PHONY: koji-no-compat
## Initiate a koji build of python-lit, llvm, clang and lld using the
## SRPMs for these packages.
## NOTE: The SRPMs can be generated using "make all-srpms".
koji-no-compat: koji-llvm \
				koji-wait-repo-llvm \
				koji-python-lit \
				koji-wait-repo-python-lit \
				koji-clang \
				koji-wait-repo-clang \
				koji-lld \
				koji-wait-repo-lld \
				koji-tag-no-compat \
				koji-create-repo

.PHONY: koji-wait-repo-%
## Waits for 30 minutes on the RPM of the given project to appear in the repo for
## the build tag.
koji-wait-repo-%:
	$(eval project:=$(subst koji-wait-repo-,,$@))
	koji --config=koji.conf -p koji-clang wait-repo --build=$(shell basename $(out)/$(project)/SRPMS/*.src.rpm | sed  -s 's/\.src\.rpm$$//' | sed 's/fc[0-9]\+/fc$(FEDORA_VERSION)/') --timeout=30 $(KOJI_TAG)-build

.PHONY: koji-%
## Takes the SRPM for the given project and builds it on koji
koji-%:
	$(eval project:=$(subst koji-,,$@))
	koji --config=koji.conf -p koji-clang build --wait $(KOJI_TAG) $(out)/$(project)/SRPMS/*.src.rpm

.PHONY: koji-tag-no-compat
koji-tag-no-compat:
	$(eval $(call get-nvr,llvm_nvr,llvm))
	$(eval $(call get-nvr,clang_nvr,clang))
	$(eval $(call get-nvr,lld_nvr,lld))
	koji --config=koji.conf -p koji-clang tag-build $(KOJI_TAG) $(llvm_nvr) $(clang_nvr) $(lld_nvr)

.PHONY: koji-tag-compat
koji-tag-compat:
	$(eval $(call get-nvr,llvm_nvr,llvm12))
	$(eval $(call get-nvr,clang_nvr,clang12))
	koji --config=koji.conf -p koji-clang tag-build $(KOJI_TAG) $(llvm_nvr) $(clang_nvr)

.PHONY: koji-create-repo
koji-create-repo:
	koji --config=koji.conf -p koji-clang dist-repo --allow-missing-signatures $(KOJI_TAG)

# Provide "make help"
include ./help.mk
