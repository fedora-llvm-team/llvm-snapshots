yyyymmdd ?= $(shell date +%Y%m%d)

.PHONY: all
all: snapshot

.PHONY: clean
clean:
	rm -rf out/

.PHONY: snapshot
snapshot: compat-llvm compat-clang python-lit llvm clang lld compiler-rt mlir lldb

.PHONY: llvm clang python-lit lld compiler-rt mlir lldb
llvm clang python-lit lld compiler-rt mlir lldb:
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "$@"

.PHONY: compat-llvm compat-clang
compat-llvm compat-clang:
	$(eval pkg:=$(subst compat-,,$@))
	echo ${pkg}
	./build.sh --koji-build-rpm --koji-wait-for-build --build-compat-packages --yyyymmdd ${yyyymmdd} --verbose --projects "${pkg}"