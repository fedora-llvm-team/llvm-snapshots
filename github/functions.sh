set +x

# set -e
# TODO(kwk): Is there a better way to check project existence?
# TODO(kwk): Maybe: copr list $username | grep --regexp="^Name: \$project$"
function project_exists(){
  local project=$1;
  copr get-chroot $project/fedora-rawhide-x86_64 > /dev/null 2>&1 \
  && echo "true" || echo "false";
}

function get_active_build_ids(){
  local project=$1;
  copr list-builds --output-format text-row $project \
    | grep --perl-regexp --regexp='(running|waiting|pending|importing|starting)' \
    | cut -f 1
}

# Prints the chroots we care about.
function get_chroots() {
  copr list-chroots | grep -P '^fedora-(rawhide|[0-9]+)' | tr '\n' ' '
}

# Prints the packages we care about
function get_packages() {
  echo "python-lit llvm clang lld compiler-rt libomp"
}

# Returns false if a package needs special handling on certain architectures
function is_package_supported_by_chroot() {
  local pkg=$1;
  local chroot=$2;

  if [[ ("$pkg" == "lld" || "$pkg" == "libomp") && $chroot =~ -s390x$ ]]; then
    false
  else
    true
  fi
}

# Returns 0 if all packages on all* chroots have successful builds.
#
# *: All supported combinations of package + chroot (see is_package_supported_by_chroot).
function has_all_good_builds(){
  local project=$1;

  copr monitor --output-format text-row --fields state,chroot,name $project | sort -k1 -k2 -k3 > /tmp/actual.txt
  truncate -s 0 /tmp/expected.txt
  for chroot in $(get_chroots); do
    for package in $(get_packages) llvm-snapshot-builder; do
      if is_package_supported_by_chroot "$package" "$chroot"; then
        echo "succeeded $chroot $package" >> /tmp/expected.txt
      fi
    done
  done
  sort -k1 -k2 -k3 -o /tmp/expected.txt /tmp/expected.txt
  diff -bus /tmp/expected.txt /tmp/actual.txt
}

# This installs the gh client for Fedora as described here:
# https://github.com/cli/cli/blob/trunk/docs/install_linux.md#fedora-centos-red-hat-enterprise-linux-dnf
function install_gh_client() {
  dnf install -y 'dnf-command(config-manager)'
  dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
  dnf install -y gh
}
