# This file contains overwrite for the functions in functions.sh
set -x

# Prints the chroots we care about.
function get_chroots() {
  copr list-chroots | grep -P '^(fedora-(rawhide|[0-9]+)|rhel-9-)' | sort |  tr '\n' ' '
}

# Prints the packages we care about
# overwrite
function get_packages() {
  echo "llvm"
}
