FROM registry.fedoraproject.org/fedora:41

RUN dnf -y copr enable tstellar/fedora-clang-default-cc

RUN dnf -y install jq cmake ninja-build git binutils-devel clang fedora-clang-default-cc rpmbuild

WORKDIR /root

RUN git clone https://github.com/llvm/llvm-project

WORKDIR /root/llvm-project

ADD bisect.sh git-bisect-script.sh .
