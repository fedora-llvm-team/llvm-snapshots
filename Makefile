yyyymmdd ?= $(shell date +%Y%m%d)

.PHONY: all
all: snapshot

.PHONY: clean
clean:
	rm -rf out/

.PHONY: snapshot
snapshot: compat-llvm compat-clang python-lit llvm clang lld compiler-rt mlir lldb
	
.PHONY: compat-llvm
compat-llvm:
	./build.sh --koji-build-rpm --koji-wait-for-build --build-compat-packages --yyyymmdd ${yyyymmdd} --verbose --projects "llvm" 

.PHONY: compat-clang
compat-clang:
	./build.sh --koji-build-rpm --koji-wait-for-build --build-compat-packages --yyyymmdd ${yyyymmdd} --verbose --projects "clang"

.PHONY: python-lit
python-lit:
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "python-lit"

.PHONY: llvm
llvm:
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "llvm"

.PHONY: clang
clang:
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "clang"

.PHONY: lld
lld:
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "lld"

.PHONY: compiler-rt
compiler-rt:
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "compiler-rt"

.PHONY: mlir
mlir:
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "mlir"

.PHONY: lldb
lldb:
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "lldb"


