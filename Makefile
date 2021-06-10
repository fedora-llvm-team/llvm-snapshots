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

define build-project
	$(eval project:=$(1))
	$(eval mounts:=$(2))
	$(eval enabled_repos:=$(3))
	mkdir -pv out/${project}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/${project}:/home/johndoe/rpmbuild:Z ${mounts} \
		builder \
			--reset-project \
			--generate-spec-file \
			--build-srpm \
			--install-build-dependencies \
			--build-rpm \
			--generate-dnf-repo \
			--yyyymmdd ${yyyymmdd} \
			--project ${project} ${enabled_repos} \
	|& tee out/build-${project}.log
endef

define mount-opts
-v $(shell pwd)/out/$(1)/RPMS:/repo-$(1):Z
endef

define enable-dnf-repo
--enable-dnf-repo /repo-$(1)
endef

mounts_python_lit :=
mounts_llvm := $(call mount-opts,python-lit)
mounts_clang := $(foreach p,python-lit llvm,$(call mount-opts,$(p)))
mounts_lld := $(foreach p,python-lit llvm clang,$(call mount-opts,$(p)))

mounts_python_lit :=
repos_llvm := $(call enable-dnf-repo,python-lit)
repos_clang := $(foreach p,python-lit llvm,$(call enable-dnf-repo,$(p)))
repos_lld := $(foreach p,python-lit llvm clang,$(call enable-dnf-repo,$(p)))



# TARGETS:



.PHONY: all
all: python-lit compat-llvm compat-clang llvm clang lld

.PHONY: clean
clean:
	rm -rf out

.PHONY: clean-cache
clean-cache:
	rm -rf dnf-cache

./out/python-lit:
	@mkdir -pv ./out/python-lit

./dnf-cache:
	mkdir -p dnf-cache

.PHONY: container-image
container-image: ./dnf-cache
	$(CONTAINER_TOOL) build --quiet --tag builder .

.PHONY: python-lit
python-lit: $(CONTAINER_DEPENDENCIES)
	$(call build-project,python-lit)

.PHONY: llvm
llvm: $(CONTAINER_DEPENDENCIES)
	$(call build-project,llvm,$(mounts_llvm),$(repos_llvm))

.PHONY: clang
clang: $(CONTAINER_DEPENDENCIES)
	$(call build-project,clang,$(mounts_clang),$(repos_clang))

.PHONY: lld
lld: $(CONTAINER_DEPENDENCIES)
	$(call build-project,lld,${mounts_lld},$(repos_lld))



# SPECIAL TARGETS:



# This mounts a project and with all dependent repos mounted (expecting they
# exist) and then enter a bash-shell for experiments or rerunning tests and
# whatnot ;)
.PHONY: shell-%
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