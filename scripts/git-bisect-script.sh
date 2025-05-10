#!/bin/bash

srpm_name=$1

if ! ninja -C build install-clang install-clang-resource-headers install-LLVMgold install-llvm-ar install-llvm-ranlib; then
  exit 125
fi

rpmbuild -D '%toolchain clang' -rb $srpm_name
