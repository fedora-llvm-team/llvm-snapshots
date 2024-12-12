FROM registry.fedoraproject.org/fedora:41

ENV LLVM_SYSROOT=/opt/llvm \
    AR=llvm-ar \
    RANLIB=llvm-ranlib

RUN dnf -y copr enable tstellar/fedora-clang-default-cc

RUN dnf -y install jq cmake ninja-build git binutils-devel clang fedora-clang-default-cc rpmbuild ccache

WORKDIR /root

RUN git clone https://github.com/llvm/llvm-project

WORKDIR /root/llvm-project

ADD bisect.sh git-bisect-script.sh .

COPY --from=ghcr.io/llvm/ci-ubuntu-22.04:1734145213 $LLVM_SYSROOT $LLVM_SYSROOT

