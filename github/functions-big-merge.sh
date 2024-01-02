# This file contains overwrite for the functions in functions.sh
set +x

# overwrite
function was_broken_snapshot_detected_today() {
  local d=`yyyymmdd`
  gh --repo ${GITHUB_REPOSITORY} issue list \
    --label broken_snapshot_detected \
    --label big-merge \
    --state all \
  | grep -P "$d" > /dev/null 2>&1
}

# Prints the packages we care about
# overwrite
function get_packages() {
  echo "llvm"
}
