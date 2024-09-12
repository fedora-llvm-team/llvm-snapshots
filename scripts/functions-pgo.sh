set -x

# Prints the chroots we care about.
function get_chroots() {
  copr list-chroots | grep -P '^(fedora-(rawhide|[0-9]+)|rhel-[8,9]-|centos-stream-10)' | sort |  tr '\n' ' '
}
