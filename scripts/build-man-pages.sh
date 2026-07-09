#!/usr/bin/bash

set -x
set -e

yyyymmdd=$(date +%Y%m%d)

function help {
    cat <<EOF
Generates a man pages tarball for a given git revision of the LLVM repository.
The tarball will get the name: llvm_man_pages-YYYYMMD.tar.xz with YYYYMMDD
replaced by the date.

Usage: $(basename "$0") [-g|h|]

Options:
    -h   Print this help text and exit
    -g   LLVM git revision (e.g. 97021d5b9ac161f88bffc802756ce78ecacaa18d)
    -d   [Optional] Date in YYYYMMDD format, defaults to ${yyyymmdd}.
EOF
}

while getopts ":hdg:" option; do
   case $option in
      h)
         help
         exit;;
      d)
         yyyymmdd=$OPTARG;;
      g)
         llvm_snapshot_git_revision=$OPTARG;;
     \?)
         echo "Error: Invalid option"
         exit;;
   esac
done

echo "yyyymmdd=${yyyymmdd}"
echo "llvm_snapshot_git_revision=${llvm_snapshot_git_revision}"

if [ -z "${llvm_snapshot_git_revision}" ]; then
    echo "ERROR: Must specify LLVM git revision with (see -g option)." 1>&2
    exit 1
fi

echo "[INFO] Download and extract the LLVM source tarball"

if [ ! -e "${llvm_snapshot_git_revision}.tar.gz" ]; then
    curl -sLO "https://github.com/llvm/llvm-project/archive/${llvm_snapshot_git_revision}.tar.gz"
fi

if [ ! -d "llvm-project-${llvm_snapshot_git_revision}" ]; then
    tar xzf "${llvm_snapshot_git_revision}.tar.gz"
fi

echo "[INFO] Install python dependencies for building the man pages in virtual environment"

python -m venv build-docs
source ./build-docs/bin/activate

pip install -r ./llvm-project-${llvm_snapshot_git_revision}/llvm/docs/requirements.txt

echo "[INFO] Build the man pages"

pushd "./llvm-project-${llvm_snapshot_git_revision}/"
./llvm/utils/release/build-docs.sh -no-doxygen -no-sphinx
popd

deactivate

echo "[INFO] Re-package the man pages"

# NOTE: The build-docs.sh script executes "git rev-parse HEAD" which will lead
# the git revision of this very repository which is wrong. We re-package the man
# pages ourselves again to fix the release and git revision.

spec_git_rev=$(git rev-parse HEAD)

man_page_dir="llvm_man_pages-${yyyymmdd}"

mv -v "./llvm-project-${llvm_snapshot_git_revision}/llvm_man_pages--g${spec_git_rev:0:14}" "${man_page_dir}"

tar -cJf "${man_page_dir}.tar.xz" "${man_page_dir}"
