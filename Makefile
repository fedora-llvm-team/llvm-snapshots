# It's necessary to set this because some environments don't link sh -> bash.
SHELL := /bin/bash

yyyymmdd ?= $(shell date +%Y%m%d)

# If your user requires sudo to run either docker or podman, try this:
#
#     make CONTAINER_TOOL="sudo podman" <WHATERVER_TARGET>
CONTAINER_TOOL ?= docker
# By default we cache DNF packages because it allows us for avoiding re-download
# problems. To disable DNF caching, do this:
#
#    make CONTAINER_DNF_CACHE= <WHATERVER_TARGET>
CONTAINER_DNF_CACHE ?= -v $(shell pwd)/dnf-cache:/var/cache/dnf:Z
# This exists so that generated files inside the container can be edited from
# the outside as the user running the container.
CONTAINER_PERMS ?= -u $(shell id -u $(USER)):$(shell id -g $(USER))
# Whether to run a container interactively or not.
CONTAINER_INTERACTIVE_SWITCH ?= -i
CONTAINER_RUN_OPTS =  -t --rm $(CONTAINER_INTERACTIVE_SWITCH) $(CONTAINER_PERMS) $(CONTAINER_DNF_CACHE) -v $(shell pwd)/cfg:/home/johndoe/cfg:ro
CONTAINER_DEPENDENCIES = container-image ./dnf-cache

define build-project-srpm
	$(eval project:=$(1))
	$(eval mounts:=$(2))
	mkdir -pv out/${project}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/${project}:/home/johndoe/rpmbuild:Z \
		builder \
			--reset-project \
			--generate-spec-file \
			--build-srpm \
			--yyyymmdd ${yyyymmdd} \
			--project ${project} \
	|& tee out/build-srpm-${project}.log
endef

define build-project-rpm
	$(eval project:=$(1))
	$(eval mounts:=$(2))
	$(eval enabled_repos:=$(3))
	mkdir -pv out/${project}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/${project}:/home/johndoe/rpmbuild:Z ${mounts} \
		builder \
			--install-build-dependencies \
			--build-rpm \
			--generate-dnf-repo \
			--yyyymmdd ${yyyymmdd} \
			--project ${project} ${enabled_repos} \
	|& tee out/build-rpm-${project}.log
endef

define mount-opts
-v $(shell pwd)/out/$(1)/RPMS:/repo-$(1):Z
endef

define enable-dnf-repo
--enable-dnf-repo /repo-$(1)
endef

mounts_compat_llvm :=
mounts_compat_clang := $(call mount-opts,compat-llvm)
mounts_python_lit :=
mounts_llvm := $(call mount-opts,python-lit)
mounts_clang := $(foreach p,python-lit llvm,$(call mount-opts,$(p)))
mounts_lld := $(foreach p,python-lit llvm clang,$(call mount-opts,$(p)))

repos_compat_llvm :=
repos_compat_clang := $(call enable-dnf-repo,compat-llvm) 
repos_python_lit :=
repos_llvm := $(call enable-dnf-repo,python-lit)
repos_clang := $(foreach p,python-lit llvm,$(call enable-dnf-repo,$(p)))
repos_lld := $(foreach p,python-lit llvm clang,$(call enable-dnf-repo,$(p)))



# TARGETS:



.PHONY: all
## Build all of LLVM's sub-projects in the correct order.
all: all-srpms python-lit compat-llvm compat-clang llvm clang lld

.PHONY: all-srpms
## Build all SRPMS for all of LLVM's sub-projects.
## NOTE: With "make srpm-<PROJECT> you can build an SRPM for an individual LLVM
## sub-project.
all-srpms: srpm-python-lit srpm-compat-llvm srpm-compat-clang srpm-llvm srpm-clang srpm-lld

.PHONY: srpm-%
srpm-%: $(CONTAINER_DEPENDENCIES)
	$(eval project:=$(subst srpm-,,$@))
	$(call build-project-srpm,$(project))

.PHONY: clean
## Remove the ./out artifacts directory.
## NOTE: You can also call "make clean-<PROJECT>" to remove the artifacts for an
## individual project only.
clean:
	rm -rf out

.PHONY: clean-%
# Remove an individual project's directory in 
clean-%:
	$(eval project:=$(subst clean-,,$@))
	rm -rf out/$(project)

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
	$(CONTAINER_TOOL) build --quiet --tag builder .

.PHONY: python-lit
## Build LLVM's python-lit sub-project.
python-lit: srpm-python-lit $(CONTAINER_DEPENDENCIES)
	$(call build-project-rpm,python-lit)

.PHONY: compat-llvm
## Build the compatibility packages for LLVM's llvm sub-project.
compat-llvm: srpm-compat-llvm $(CONTAINER_DEPENDENCIES)
	$(call build-project-rpm,compat-llvm,$(mounts_compat_llvm),$(repos_compat_llvm))

.PHONY: compat-clang
## Build the compatibility packages for LLVM's clang sub-project.
compat-clang: srpm-compat-clang $(CONTAINER_DEPENDENCIES)
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
# This mounts a project and with all dependent repos mounted (expecting they
# exist) and then enter a bash-shell for experiments or rerunning tests and
# whatnot 
shell-%:
	$(eval project:=$(subst shell-,,$@))
	$(eval project_var:=$(subst -,_,$(project)))
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/$(project):/home/johndoe/rpmbuild:Z $(mounts_$(project_var)) \
		builder \
			--shell \
			--yyyymmdd ${yyyymmdd} \
			--project $(project) $(repos_$(project_var)) \
	|& tee out/shell-$(project).log

# Provide "make help"
include ./help.mk