# This file contains overwrite for the functions in functions.sh
set +x

# Prints the chroots we care about.
prefix_function get_chroots
function get_chroots() {
  _get_chroots
  echo -n " rhel-9-x86_64 "
}

# Prints the packages we care about
# overwrite
function get_packages() {
  echo "llvm"
}
