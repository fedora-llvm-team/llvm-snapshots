yyyymmdd ?= $(shell date +%Y%m%d)

.PHONY: all
all: snapshot

.PHONY: clean
clean:
	rm -rfv out/

.PHONY: snapshot
snapshot:	compat-llvm \
			compat-clang \
			python-lit \
			llvm \
			clang \
			lld \
			compiler-rt \
			mlir \
			lldb

.PHONY: koji-snapshot
koji-snapshot: 	koji-compat-llvm \
				koji-compat-clang \
				koji-python-lit \
				koji-llvm \
				koji-clang \
				koji-lld \
				koji-compiler-rt \
				koji-mlir \
				koji-lldb

.PHONY: koji-python-lit  koji-llvm koji-clang koji-lld koji-compiler-rt koji-mlir koji-lldb
koji-python-lit koji-llvm koji-clang koji-lld koji-compiler-rt koji-mlir koji-lldb:
	$(eval pkg:=$(subst koji-,,$@))
	./build.sh --koji-build-rpm --koji-wait-for-build --yyyymmdd ${yyyymmdd} --verbose --projects "${pkg}"

.PHONY: koji-compat-llvm koji-compat-clang
koji-compat-llvm koji-compat-clang:
	$(eval pkg:=$(subst koji-compat-,,$@))
	./build.sh --koji-build-rpm --koji-wait-for-build --build-compat-packages --yyyymmdd ${yyyymmdd} --verbose --projects "${pkg}"

.PHONY:  python-lit llvm clang lld compiler-rt mlir lldb
python-lit llvm clang lld compiler-rt mlir lldb:
	./build.sh --mock-build-rpm --mock-check-rpm --yyyymmdd ${yyyymmdd} --verbose --projects "$@"

.PHONY: compat-llvm compat-clang
compat-llvm compat-clang:
	$(eval pkg:=$(subst koji-compat-,,$@))
	./build.sh --mock-build-rpm --mock-check-rpm --build-compat-packages --yyyymmdd ${yyyymmdd} --verbose --projects "${pkg}"