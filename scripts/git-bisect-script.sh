#!/bin/bash

srpm_name=$1

ninja -C build install-clang install-clang-resource-headers install-LLVMgold install-llvm-ar install-llvm-ranlib

rpmbuild -rb $srpm_name
