# This file contains overwrite for the functions in functions.sh
set +x

# Prints the chroots we care about.
function get_chroots() {
  echo "fedora-40-x86_64"
}

# Prints the packages we care about
# overwrite
function get_packages() {
  echo "llvm"
}
