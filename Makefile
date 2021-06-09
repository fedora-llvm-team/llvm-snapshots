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
CONTAINER_DEPENDENCIES = image ./dnf-cache

# .PHONY: all
# all: snapshot

.PHONY: clean
clean:
	rm -rf out

.PHONY: clean-cache
clean-cache:
	rm -rf dnf-cache

.PHONY: koji-compat
koji-compat: koji-compat-llvm \
			 koji-compat-clang

.PHONY: srpms
srpms:
	rm -rfv shared
	mkdir -pv shared
	./build.sh --yyyymmdd ${yyyymmdd} --verbose --out-dir shared --projects "llvm clang" --build-compat-packages |& tee shared/make.log
	./build.sh --yyyymmdd ${yyyymmdd} --verbose --out-dir shared |& tee --append shared/make.log

.PHONY: snapshot
snapshot:	compat-llvm \
			compat-clang \
			python-lit \
			llvm \
			clang \
			lld \
			compiler-rt \
			libomp \
			mlir \
			lldb

.PHONY: koji-snapshot
koji-snapshot: 	koji-python-lit \
				koji-llvm \
				koji-clang \
				koji-lld \
				koji-compiler-rt \
				koji-libomp \
				koji-mlir \
				koji-lldb

.PHONY: koji-python-lit  koji-llvm koji-clang koji-lld koji-compiler-rt koji-libomp koji-mlir koji-lldb
koji-python-lit koji-llvm koji-clang koji-lld koji-compiler-rt koji-libomp koji-mlir koji-lldb:
	$(eval pkg:=$(subst koji-,,$@))
	./build.sh --out-dir koji-out --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "${pkg}" --skip-srpm-generation --srpms-dir shared/srpms |& tee koji-out/build-${pkg}.log

.PHONY: koji-compat-llvm koji-compat-clang
koji-compat-llvm koji-compat-clang:
	$(eval pkg:=$(subst koji-compat-,,$@))
	./build.sh --out-dir koji-out --koji-build-rpm --koji-wait-for-build --build-compat-packages --yyyymmdd ${yyyymmdd} --verbose --projects "${pkg}" --skip-srpm-generation --srpms-dir shared/srpms |& tee koji-out/build-${pkg}.log

.PHONY:  python-lit llvm clang lld compiler-rt libomp mlir lldb
python-lit llvm clang lld compiler-rt libomp mlir lldb:
	./build.sh --out-dir mock-out --mock-build-rpm --mock-check-rpm --yyyymmdd ${yyyymmdd} --verbose --projects "$@" --skip-srpm-generation --srpms-dir shared/srpms |& tee mock-out/build-${pkg}.log

.PHONY: compat-llvm compat-clang
compat-llvm compat-clang:
	$(eval pkg:=$(subst compat-,,$@))
	./build.sh --out-dir mock-out --mock-build-rpm --mock-check-rpm --build-compat-packages --yyyymmdd ${yyyymmdd} --verbose --projects "${pkg}" --skip-srpm-generation --srpms-dir shared/srpms |& tee mock-out/build-${pkg}.log


# .PHONY: docker-build-python-lit
# docker-build-python-lit: docker-image
# 	docker run -it --rm \
# 		-v $(shell pwd)/out/projects/python-lit:/home/johndoe/rpmbuild:Z \
# 		builder \
# 		build-srpm.sh --spec-file SPECS/python-lit.snapshot.spec
# 		./build.sh --out-dir out --mock-build-rpm --mock-check-rpm --yyyymmdd ${yyyymmdd} --verbose --projects "$@" --skip-srpm-generation --srpms-dir shared/srpms |& tee mock-out/build-${pkg}.log


# 		# -u $(shell id -u $(USER)):$(shell id -g $(USER)) \

./out/python-lit:
	@mkdir -pv ./out/python-lit


./dnf-cache:
	mkdir -p dnf-cache

define dependency-pkgs
[[ "$(1)" == "clang" ]] && echo "llvm"; \
[[ "$(1)" == "lld" ]] && echo "llvm1";
endef

.PHONY: foo
foo:
	$(call dependency-pkgs,clang)

a.c:
	echo "a"
b.c: a.c
	echo "b"
c.c: b.c
	echo "c"

.PHONY: image
image: ./dnf-cache
	$(CONTAINER_TOOL) build --quiet --tag builder .

.PHONY: one-python-lit one-llvm one-clang one-lld one-compiler-rt one-libomp one-mlir one-lldb
one-python-lit one-llvm one-clang one-lld one-compiler-rt one-libomp one-mlir one-lldb: $(CONTAINER_DEPENDENCIES)
	$(eval pkg:=$(subst one-,,$@))
	mkdir -pv out/${pkg}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/${pkg}:/home/johndoe/rpmbuild:Z \
		builder \
			--reset-project \
			--generate-spec-file \
			--build-srpm \
			--install-build-dependencies \
			--build-rpm \
			--generate-dnf-repo \
			--yyyymmdd ${yyyymmdd} \
			--project ${pkg} \
	|& tee out/${pkg}-allinone.log

.PHONY: reset-python-lit reset-llvm reset-clang reset-lld reset-compiler-rt reset-libomp reset-mlir reset-lldb
reset-python-lit reset-llvm reset-clang reset-lld reset-compiler-rt reset-libomp reset-mlir reset-lldb: $(CONTAINER_DEPENDENCIES)
	$(eval pkg:=$(subst spec-,,$@))
	mkdir -pv out/${pkg}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/${pkg}:/home/johndoe/rpmbuild:Z \
		builder \
			--verbose \
			--reset-project \
			--yyyymmdd ${yyyymmdd} \
			--project ${pkg} \
	|& tee out/${pkg}-spec.log

.PHONY: spec-python-lit spec-llvm spec-clang spec-lld spec-compiler-rt spec-libomp spec-mlir spec-lldb
spec-python-lit spec-llvm spec-clang spec-lld spec-compiler-rt spec-libomp spec-mlir spec-lldb: $(CONTAINER_DEPENDENCIES)
	$(eval pkg:=$(subst spec-,,$@))
	mkdir -pv out/${pkg}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/${pkg}:/home/johndoe/rpmbuild:Z \
		builder \
			--generate-spec-file \
			--yyyymmdd ${yyyymmdd} \
			--project ${pkg} \
	|& tee out/${pkg}-spec.log

.PHONY: srpm-python-lit srpm-llvm srpm-clang srpm-lld srpm-compiler-rt srpm-libomp srpm-mlir srpm-lldb
srpm-python-lit srpm-llvm srpm-clang srpm-lld srpm-compiler-rt srpm-libomp srpm-mlir srpm-lldb: $(CONTAINER_DEPENDENCIES)
	$(eval pkg:=$(subst srpm-,,$@))
	mkdir -pv out/${pkg}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/${pkg}:/home/johndoe/rpmbuild:Z \
		builder \
			--build-srpm \
			--yyyymmdd ${yyyymmdd} \
			--project ${pkg} \
	|& tee out/${pkg}-srpm.log

.PHONY: rpm-python-lit rpm-llvm rpm-clang rpm-lld rpm-compiler-rt rpm-libomp rpm-mlir rpm-lldb
rpm-python-lit rpm-llvm rpm-clang rpm-lld rpm-compiler-rt rpm-libomp rpm-mlir rpm-lldb: $(CONTAINER_DEPENDENCIES)
	$(eval pkg:=$(subst rpm-,,$@))
	mkdir -pv out/${pkg}
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/${pkg}:/home/johndoe/rpmbuild:Z \
		builder \
			--install-build-dependencies \
			--build-rpm \
			--generate-dnf-repo \
			--yyyymmdd ${yyyymmdd} \
			--project ${pkg} \
	|& tee out/${pkg}-rpm.log

.PHONY: all
all: spec-python-lit srpm-python-lit rpm-python-lit \
	 spec-llvm srpm-llvm rpm-llvm

.PHONY: test
test: image
	$(CONTAINER_TOOL) run $(CONTAINER_RUN_OPTS) \
		-v $(shell pwd)/out/python-lit:/home/johndoe/rpmbuild:Z \
		-v $(shell pwd)/out/python-lit/RPMS:/home/johndoe/repo-python-lit:ro \
		builder \
			--shell \
			--enable-dnf-repo /home/johndoe/repo-python-lit \
			--yyyymmdd ${yyyymmdd} \
			--project python-lit \


# \

# docker run \
# 	-it \
# 	--rm \
# 	-v $(shell pwd)/out/python-lit:/home/johndoe/rpmbuild:Z \
# 	-u $(shell id -u $(USER)):$(shell id -g $(USER)) \
# 	builder \
# 	    --yyyymmdd ${yyyymmdd} \
# 		--project python-lit \
# |& tee -a out/build-python-lit.log

# docker run \
# 	-it \
# 	--rm \
# 	-v $(shell pwd)/out/python-lit:/home/johndoe/rpmbuild:Z \
# 	builder \
# 	build.sh \
# 		--yyyymmdd ${yyyymmdd} \
# 		--verbose \
# 		--project python-lit \
# |& tee --append out/build-python-lit.log

# -u $(shell id -u $(USER)):$(shell id -g $(USER)) \

# .PHONY: docker-build-python-lit
# docker-build-python-lit: image
# 	docker run -it --rm \
# 		-v $(shell pwd)/out/projects/python-lit:/home/johndoe/rpmbuild:Z \
# 		builder \
# 		build-srpm.sh --spec-file SPECS/python-lit.snapshot.spec
# 		# -u $(shell id -u $(USER)):$(shell id -g $(USER)) \