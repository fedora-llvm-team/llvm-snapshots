#!/bin/env bash

# When run, this script produces a directory structure like this:
#
#       /tmp/tmp.MjjC8dNVlC
#       ├── new
#       │   ├── clang-analyzer.txt
#       │   ├── clang-devel.txt
#       │   ├── clang-libs.txt
#       │   ├── ...
#       │   ├── version.txt
#       └── old
#           ├── clang-analyzer.txt
#           ├── clang-devel.txt
#           ├── clang-libs.txt
#           ├── ...
#           ├── clang-libs.txt
#
# The "old" and "new" directories refer to "rawhide" and "snapshots".
# The "version.txt" file contains the output of "clang --version".
#
# With a tool like "meld" you can get a nice representation of differences
# between the old and the new package contents as we currently package it on
# rawhide and for the snapshots.

set -e

echo "Check for all required packages:"
rpm -q podman meld copr-cli diffutils grep

RESULTDIR=$(mktemp -d)
CONTAINERFILE=$(mktemp)

cat <<EOF > $CONTAINERFILE
FROM fedora:rawhide AS old

ARG INTERESTING_PKGS
RUN dnf install -y \${INTERESTING_PKGS} --setopt=install_weak_deps=False

FROM fedora:rawhide AS new

ARG INTERESTING_PKGS
RUN dnf install -y 'dnf5-command(copr)'
RUN dnf copr enable -y @fedora-llvm-team/llvm-snapshots
RUN dnf install -y \${INTERESTING_PKGS} --setopt=install_weak_deps=False
EOF

# Get list of packages that we're interested in:
copr_project=@fedora-llvm-team/llvm-snapshots
chroot=fedora-rawhide-x86_64
build_url=$(copr-cli monitor --output-format text-row --fields "chroot,url_build" $copr_project | grep -Po "$chroot\s*\Khttps://.*")
echo $build_url
packages=$(curl -sL $build_url \
| grep -Po "<dd>\K.*? [^<]+" \
| grep -Po "^[^ ]+" \
| grep -v -- Build \
| grep -v -- -debuginfo \
| grep -v -- llvm-build-stats \
| grep -v -- -debugsource)
echo $packages

podman build -f $CONTAINERFILE --build-arg INTERESTING_PKGS="$packages" --target old -t compare:old
podman build -f $CONTAINERFILE --build-arg INTERESTING_PKGS="$packages" --target new -t compare:new

mkdir -pv $RESULTDIR/{old,new}

podman run -it compare:old bash -c "clang --version" > $RESULTDIR/old/version.txt
podman run -it compare:new bash -c "clang --version" > $RESULTDIR/new/version.txt

for PKG in $packages; do
    echo "Getting package contents for package: $PKG"
    podman run -it compare:old bash -c "rpm -ql $PKG" | grep -v .build-id | sort > $RESULTDIR/old/$PKG.txt
    podman run -it compare:new bash -c "rpm -ql $PKG" | grep -v .build-id | sort > $RESULTDIR/new/$PKG.txt
done

echo "Done writing package contents to $RESULTDIR"

meld $RESULTDIR/old $RESULTDIR/new
