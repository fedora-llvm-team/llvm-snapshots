set -x

# Prints the year month and day combination for today
function yyyymmdd() {
  date +%Y%m%d
}

# Checks if a copr project exists
function copr_project_exists(){
  local project=$1;
  copr get $project > /dev/null 2>&1
}

# set -e
# TODO(kwk): get rid of echoing "true" and "false"
function project_exists(){
  local project=$1
  copr_project_exists $project && echo "true" || echo "false";
}

function get_active_build_ids(){
  local project=$1;
  copr list-builds --output-format text-row $project \
    | grep --perl-regexp --regexp='(running|waiting|pending|importing|starting)' \
    | cut -f 1
}

# Prints the chroots we care about.
function get_chroots() {
  copr list-chroots | grep -P '^(fedora-(rawhide|[0-9]+)|rhel-[8,9]-)' | sort |  tr '\n' ' '
}

# Returns 0 if all llvm packages on all chroots have successful builds.
function has_all_good_builds(){
  local project=$1

  copr monitor --output-format text-row --fields state,chroot,name $project | sort -k1 -k2 -k3 > /tmp/actual.txt
  truncate -s 0 /tmp/expected.txt
  for chroot in $(get_chroots); do
    echo "succeeded $chroot llvm" >> /tmp/expected.txt
  done
  sort -k1 -k2 -k3 -o /tmp/expected.txt /tmp/expected.txt
  diff -bus /tmp/expected.txt /tmp/actual.txt
}

#endregion
