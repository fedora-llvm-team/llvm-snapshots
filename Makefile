yyyymmdd ?= $(shell date +%Y%m%d)

.PHONY: all
all: snapshot


.PHONY: clean
clean:
	rm -rfv out shared koji-out mock-out

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