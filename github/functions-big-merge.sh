# This file contains overwrite for the functions in functions.sh
set +x

# Prefixes the old version of the given function with "_" to make it callable
# from the overwriting function.
function overwrite_function() {
  local function_name=$1
  eval "_`declare -f $function_name`"
}

# overwrite
function was_broken_snapshot_detected_today() {
  local d=`yyyymmdd`
  gh --repo ${GITHUB_REPOSITORY} issue list \
    --label broken_snapshot_detected \
    --label strategy/big-merge \
    --state all \
    --search "$d" \
  | grep -P "$d" > /dev/null 2>&1
}

# Prints the chroots we care about.
overwrite_function get_chroots
function get_chroots() {
  _get_chroots
  echo -n "rhel-9-x86_64 "
}

# Prints the packages we care about
# overwrite
function get_packages() {
  echo "llvm"
}

function get_chroots() {
  copr list-chroots | grep -P '^fedora-(rawhide|[0-9]+)' | tr '\n' ' '
}

# Prefixes the old version of the given function with "_" to make it callable
# from the overwrite.
function overwrite_function() {
  local function_name=$1
  eval "_`declare -f $function_name`"
}

overwrite_function get_chroots
function get_chroots() {
  _get_chroots
  echo -n "rhel-9-x86_64 "
}

get_chroots
