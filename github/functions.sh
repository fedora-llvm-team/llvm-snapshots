set +x

# Prints the year month and day combination for today
function yyyymmdd() {
  date +%Y%m%d
}

# Checks if there's an issue for a broken snapshot reported today
function was_broken_snapshot_detected_today() {
  local repo=$1
  local strategy=$2
  local d=`yyyymmdd`
  gh --repo $repo issue list \
    --label broken_snapshot_detected \
    --label strategy/$strategy \
    --state all \
    --search "$d" \
  | grep -P "$d" > /dev/null 2>&1
}

# Get today's issue. Make sure was_broken_snapshot_detected_today found one.
function todays_issue_number() {
  local repo=$1
  local strategy=$2
  local d=`yyyymmdd`
  gh --repo $repo issue list \
    --label broken_snapshot_detected \
    --label strategy/$strategy \
    --state all \
    --search "$d" \
    --json number \
    --jq .[0].number
}

# Checks if a copr project exists
function copr_project_exists(){
  local project=$1;
  copr get-chroot $project/fedora-rawhide-x86_64 > /dev/null 2>&1
}

# set -e
# TODO(kwk): Is there a better way to check project existence?
# TODO(kwk): Maybe: copr list $username | grep --regexp="^Name: \$project$"
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
  copr list-chroots | grep -P '^fedora-(rawhide|[0-9]+)' | sort | tr '\n' ' '
}

# Prints the packages we care about
function get_packages() {
  echo "python-lit llvm clang lld compiler-rt libomp"
}

# Returns false if a package needs special handling on certain architectures
function is_package_supported_by_chroot() {
  local pkg=$1
  local chroot=$2

  if [[ ("$pkg" == "lld") && $chroot =~ -s390x$ ]]; then
    false
  else
    true
  fi
}

# Returns 0 if all packages on all* chroots have successful builds.
#
# *: All supported combinations of package + chroot (see is_package_supported_by_chroot).
function has_all_good_builds(){
  local project=$1
  local extra_packages=$2

  copr monitor --output-format text-row --fields state,chroot,name $project | sort -k1 -k2 -k3 > /tmp/actual.txt
  truncate -s 0 /tmp/expected.txt
  for chroot in $(get_chroots); do
    for package in $(get_packages) $extra_packages; do
      if is_package_supported_by_chroot "$package" "$chroot"; then
        echo "succeeded $chroot $package" >> /tmp/expected.txt
      fi
    done
  done
  sort -k1 -k2 -k3 -o /tmp/expected.txt /tmp/expected.txt
  diff -bus /tmp/expected.txt /tmp/actual.txt
}

#region error causes

# Checks if the first issue comment contains a note on the chroot failing. The
# comment looks like <!--error/$cause project/$package chroot/$chroot-->.
function has_error_cause_comment() {
  local user_repo=$1
  local issue_number=$2
  local chroot=$3
  local package=$4
  local cause=$5

  >&2 echo "Checking for error cause comment for repo $user_repo and issue number $issue_number: chroot=$chroot"
  comment=$(gh --repo $user_repo issue view $issue_number \
    --json body \
    --jq '. | select(.body | match("<!--error/'$cause' project/'$package' chroot/'$chroot'-->"))')
  [[ -n "$comment" ]]
}

# For a given project this function prints causes for all cases of errors it can
# automatically identify (e.g. copr_timeout, network_issue). The caller needs to
# make sure the labels exists before adding them to an issue. If you pass an
# additional file name, we will write every error cause with additional
# information to it
# (<cause>;<package_name>;<chroot>;<build_log_url>;<path_to_context_file>). The
# context file contains the lines before and after the error in the build log.
function get_error_causes(){
  local project=$1
  local causes_file=$2
  local grep_opts="-n --context=3"
  local monitor_file=$(mktemp)
  local context_file=$(mktemp)

  >&2 echo "Start getting error causes from Copr monitor..."

  [[ -n "$causes_file" ]] && truncate --size 0 $causes_file

  copr monitor \
    --output-format json \
    --fields chroot,name,state,url_build_log $project \
    > $monitor_file

  cat $monitor_file | jq -r '.[] | select(.state | contains("failed")) | to_entries | map(.value) | @tsv' \
  | while IFS=$'\t' read -r chroot package_name state build_log_url; do
    >&2 echo "Found on Copr monitor: state=$state package_name=$package_name chroot=$chroot build_log_url=$build_log_url";

    log_file=$(mktemp)
    curl -sL $build_log_url | gunzip -c  > $log_file

    got_cause=0

    function store_cause() {
      local cause=$1
      echo $cause
      if [[ -n "$causes_file" ]]; then
        local line="$cause;$package_name;$chroot;$build_log_url;$context_file"
        >&2 echo "Found error cause: $line"
        echo $line >> $causes_file
        # For the next error we need to make room an create a new context file
        context_file=$(mktemp)
      fi
      got_cause=1
    }

    # Check for timeout
    if [ -n "$(grep $grep_opts '!! Copr timeout' $log_file | tee $context_file)" ]; then
      store_cause "copr_timeout"
    fi

    # Check for network issues
    if [ -n "$(grep $grep_opts 'Errors during downloading metadata for repository' $log_file | tee $context_file)" ]; then
      store_cause "network_issue"
    fi

    # Check for dependency issues
    if [ -n "$(grep $grep_opts -P '(Not all dependencies satisfied|No match for argument:)' $log_file | tee $context_file)" ]; then
      store_cause "dependency_issue"
    fi

    # Check for test issues
    if [ -n "$(pcre2grep -n --before-context=2 --after-context=10 -M '(Failed Tests|Unexpectedly Passed Tests).*(\n|.)*Total Discovered Tests:' $log_file | tee $context_file)" ]; then
      store_cause "test"
    fi

    # TODO: Feel free to add your check here (make sure to set got_cause=1)...

    if [ "$got_cause" == "0" ]; then
      # Add the tail of the log to the context file because we haven't got any better information
      tail -n 10 $log_file > $context_file
      store_cause "unknown"
    fi

    rm $log_file
  done | sort | uniq

  >&2 echo "Done getting error causes from Copr monitor."
}

function get_arch_from_chroot() {
  local chroot=$1
  echo $chroot | grep -ioP '[^-]+-[0-9,rawhide]+-\K[^\s]+'
}

function get_os_from_chroot() {
  local chroot=$1
  echo $chroot | grep -ioP '[^-]+-[0-9,rawhide]+'
}

# Takes a file with error causes and promotes unknown build causes as their own
# comment on the given issue.
#
# A causes file looks like a semicolon separated list file:
#
#  network_issue;llvm;fedora-rawhide-i386;https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/llvm-snapshots-big-merge-20240105/fedora-rawhide-i386/06865034-llvm/builder-live.log.gz;/tmp/tmp.v17rnmc4rp
#  copr_timeout;llvm;fedora-39-ppc64le;https://download.copr.fedorainfracloud.org/results/@fedora-llvm-team/llvm-snapshots-big-merge-20240105/fedora-39-ppc64le/06865030-llvm/builder-live.log.gz;/tmp/tmp.PMXc0b7uEE
function report_build_issues() {
  local github_repo=$1
  local issue_num=$2
  local causes_file_path=$3
  local maintainer_handle=$4
  local comment_body_file=""

  >&2 echo "Begin reporting build issues from causes file: $causes_file_path..."
  while IFS=';' read -r cause package_name chroot build_log_url context_file;
  do
    >&2 echo "---------------"
    >&2 echo "$cause $package_name $chroot $build_log_url $context_file"

    arch=$(get_arch_from_chroot $chroot)
    os=$(get_os_from_chroot $chroot)

    if ! has_error_cause_comment $github_repo $issue_num $chroot $package_name $cause ; then
      # Store existing comment body in a file and continously append to that file before making it the new issue comment
      comment_body_file=$(mktemp)
      gh --repo $github_repo issue view $issue_num --json body --jq ".body" > $comment_body_file


      # Wrap "more interesting" build log snippets in a <details open></details> block
      details_begin="<details>"
      if [ "$cause" == "unknown" ]; then
        details_begin="<details open>"
      fi

      cat <<EOF >> $comment_body_file
<!--error/$cause project/$package_name chroot/$chroot-->
$details_begin
<summary>
Failed to build <code>$package_name</code> on <code>$chroot</code>. Cause: <b><code>$cause</code></b>
(see <a href="$build_log_url">build log</a>) [$(date --iso-8601=hours)]
</summary>

\`\`\`
$(cat $context_file)
\`\`\`

</details>
EOF
      >&2 echo "Updating issue labels and comment for issue number $issue_num in $github_repo: project=$project chroot=$chroot cause=$cause"
      create_labels_for_archs $github_repo $arch
      create_labels_for_oses $github_repo $os
      create_labels_for_projects $github_repo $package_name
      create_labels_for_error_causes $github_repo $cause
      gh --repo $github_repo issue edit $issue_num \
        --body-file $comment_body_file \
        --add-label "error/$cause,project/$package_name,arch/$arch,os/$os"
    else
      >&2 echo "An entry for the chroot already exists: chroot=$chroot"
    fi
    >&2 echo "---------------"
  done < $causes_file_path
  >&2 echo "Done updating issue comment for issue number $issue_num in $github_repo: project=$project chroot=$chroot cause=$cause"
}

# This function inspects causes of build errors and adds a comment to today's
# issue. Maybe we can identify new causes for errors by inspecting the build
# logs.
function handle_error_causes() {
  local github_repo=$1
  local strategy=$2
  local maintainer_handle=$3
  local copr_project_today=$4
  local causes_file=$5
  local issue_number=`todays_issue_number $github_repo $strategy`
  local comment_file=`mktemp`

  >&2 echo "Handling error causes..."
  >&2 echo -n "Looking for causes file: $causes_file..."

  # If no error causes file was passed, process build logs to get
  # error causes. Also ensure the error cause labels are created.
  if [[ -z "$causes_file" || ! -f "$causes_file" ]]; then
    >&2 echo "FOUND"
    causes_file=`mktemp`
    error_causes="`get_error_causes $copr_project_today $causes_file`"
    create_labels_for_error_causes $github_repo "$error_causes"
  else
    >&2 echo "NOT FOUND"
  fi

  # Turn some error causes into their own comment.
  report_build_issues \
    $github_repo \
    "$issue_number" \
    "$causes_file" \
    "$maintainer_handle"

  >&2 echo "Done handling error causes."
}

#endregion
#region labels

# Iterates over the given labels and creates or edits each label in the list
# with the given prefix and color.
function _create_labels() {
  local repo=$1
  local labels=$2
  local label_prefix=$3
  local color=$4

  >&2 echo "Begin creating labels in $repo: $labels"
  for label in $labels; do
    local label_name=$label_prefix$label
    >&2 echo "Create label: $label_name"
    gh --repo $repo label create $label_name --color $color --force
  done
  >&2 echo "Done creating labels in $repo..."
}

function create_labels_for_error_causes() {
  local repo=$1
  local error_causes="$2"
  _create_labels $repo "$error_causes" "error/" "FBCA04"
}

function create_labels_for_archs() {
  local repo=$1
  local archs="$2"
  _create_labels $repo "$archs" "arch/" "C5DEF5"
}

function create_labels_for_oses() {
  local repo=$1
  local oses="$2"
  _create_labels $repo "$oses" "os/" "F9D0C4"
}

function create_labels_for_projects() {
  local repo=$1
  local projects="$2"
  _create_labels $repo "$projects" "project/" "BFDADC"
}

function create_labels_for_strategies() {
  local repo=$1
  local strategies="$2"
  _create_labels $repo "$strategies" "strategy/" "FFFFFF"
}
#endregion

# This installs the gh client for Fedora as described here:
# https://github.com/cli/cli/blob/trunk/docs/install_linux.md#fedora-centos-red-hat-enterprise-linux-dnf
function install_gh_client() {
  dnf install -y 'dnf-command(config-manager)'
  dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
  dnf install -y gh
}
