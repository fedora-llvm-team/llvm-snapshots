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
  local log_file=$(mktemp)

  >&2 echo "Start getting error causes from Copr monitor..."

  [[ -n "$causes_file" ]] && truncate --size 0 $causes_file

  copr monitor \
    --output-format json \
    --fields chroot,name,state,url_build_log,url_build,build_id $project \
    > $monitor_file

  cat $monitor_file | jq -r '.[] | select(.state == "failed") | to_entries | map(.value | if . then . else "NOTFOUND" end) | @tsv' \
  | while IFS=$'\t' read -r build_id chroot package_name state build_url build_log_url; do
    >&2 cat <<EOF
---------------
Package:       $package_name
State:         $state
Chroot:        $chroot
Build-Log-URL: $build_log_url
Build-URL:     $build_url
Build-ID:      $build_id
EOF

    got_cause=0

    function store_cause() {
      local cause=$1
      if [[ -n "$causes_file" ]]; then
        local line="$cause;$package_name;$chroot;$build_log_url;$build_url;$build_id;$context_file"
        >&2 echo "Cause:         $cause"
        >&2 echo "Context File:  $context_file"
        echo $line >> $causes_file
        # For the next error we need to make room an create a new context file
        context_file=$(mktemp)
      fi
      got_cause=1
    }

    # Prepend context file with markdown code fence
    function wrap_file_in_md_code_fence() {
      local context_file=$1
      sed -i '1s;^;```\n;' $context_file
      echo '```' >> $context_file
    }

    # Treat errors with no build logs as unknown and tell user to visit the
    # build URL manually.
    if [ "$build_log_url" == "NOTFOUND" ]; then
      # See https://github.com/fedora-copr/log-detective-website/issues/73#issuecomment-1889042206
      source_build_log_url="https://download.copr.fedorainfracloud.org/results/$project/srpm-builds/$(printf "%08d" $build_id)/builder-live.log.gz"
      >&2 echo "No build log found. Falling back to scanning the SRPM build log: $source_build_log_url".

      source_build_log_file=$(mktemp)
      curl -sL $source_build_log_url | gunzip -c > $source_build_log_file

      cat <<EOF >> $context_file
<h4>No build log available</h4>
Sorry, but this build contains no build log file, please consult the <a href="$build_url">build page</a> to find out more.

<h4>Errors in SRPM build log</h4>
We've scanned the <a href="$source_build_log_url">SRPM build log</a> for <code>error:</code> (case insesitive) and here's what we've found:

\`\`\`
$(grep --context=3 -i 'error:' $source_build_log_file)
\`\`\`
EOF
      store_cause "srpm_build_issue"
      continue;
    fi

    curl -sL $build_log_url | gunzip -c  > $log_file

    # Check for timeout
    if [ -n "$(grep $grep_opts '!! Copr timeout' $log_file | tee $context_file)" ]; then
      wrap_file_in_md_code_fence $context_file
      store_cause "copr_timeout"

    # Check for network issues
    elif [ -n "$(grep $grep_opts 'Errors during downloading metadata for repository' $log_file | tee $context_file)" ]; then
      wrap_file_in_md_code_fence $context_file
      store_cause "network_issue"

    # Check for dependency issues
    elif [ -n "$(grep $grep_opts -P '(No matching package to install:|Not all dependencies satisfied|No match for argument:)' $log_file | tee $context_file)" ]; then
      wrap_file_in_md_code_fence $context_file
      store_cause "dependency_issue"

    # Check for test issues
    elif [ -n "$(pcre2grep -n --after-context=10 -M '(Failed Tests|Unexpectedly Passed Tests).*(\n|.)*Total Discovered Tests:' $log_file | tee $context_file)" ]; then
      wrap_file_in_md_code_fence $context_file
      sed -i '1s;^;### Failing tests\n\n;' $context_file

      echo "" >> $context_file
      echo "### Test output" >> $context_file
      echo "" >> $context_file
      echo '```' >> $context_file
      # Extend the context by the actual test errors
      local test_output_file=$(mktemp)
      sed -n -e '/\(\*\)\{20\} TEST [^\*]* FAILED \*\{20\}/,/\*\{20\}/ p' $log_file > $test_output_file
      cat $test_output_file >> $context_file
      echo '```' >> $context_file
      store_cause "test"


    # TODO: Feel free to add your check here...
    # elif [ -n "$(grep $grep_opts 'MY PATTERN' $log_file | tee $context_file)" ]; then
    #   wrap_file_in_md_code_fence $context_file
    #   store_cause "MY_ERROR"

    fi

    if [ "$got_cause" == "0" ]; then
      cat <<EOF > $context_file
### Build log tail

Sometimes the end of the build log contains useful information.

\`\`\`
$(tail -n 10 $log_file)
\`\`\`

### RPM build errors

If we have found <code>RPM build errors</code> in the log file, you'll find them here.

\`\`\`
$(sed -n -e '/RPM build errors/,/Finish:/ p' $log_file)
\`\`\`

### Errors to look into

If we have found the term <code>error:</code> (case insentitive) in the build log,
you'll find all occurrences here together with the preceding lines.

\`\`\`
$(grep --before-context=1 -i 'error:' $log_file)
\`\`\`
EOF
      store_cause "unknown"
    fi

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

# Prints the marker after a broken snapshot issue comment body when the updates
# shall follow.
function update_marker() {
  echo '<!--UPDATES_FOLLOW_HERE-->'
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
  local comment_body_file=$(mktemp)

  # To store all important causes like "unknown"
  local sorted_causes_file=$(mktemp)
  grep -P '^unknown;' $causes_file_path | sort --stable --ignore-case > $sorted_causes_file
  # To store the rest of causes
  grep -Pv '^unknown;' $causes_file_path | sort --stable --ignore-case >> $sorted_causes_file

  # Store existing comment body in a file and continously append to that file
  # before making it the new issue comment.
  gh --repo $github_repo issue view $issue_num --json body --jq ".body" > $comment_body_file

  # Shorten body until update marker because we're gonna re-add all errors again.
  sed -i "/$(update_marker)/q" $comment_body_file

  # For older issues where the comment marker is not there yet, we'll simply add
  # it on purpose here.
  echo "$(update_marker)" >> $comment_body_file

  echo "<ol>" >> $comment_body_file

  archs=""
  oses=""
  package_names=""
  error_causes=""
  prev_cause=""

  >&2 echo "Begin reporting build issues from causes file: $causes_file_path..."
  while IFS=';' read -r cause package_name chroot build_log_url build_url build_id context_file;
  do
    >&2 cat <<EOF
----------
Cause:         $cause
Package:       $package_name
Chroot:        $chroot
Build-Log-URL: $build_log_url
Build-URL:     $build_url
Build-ID:      $build_id
Context-File:  $context_file"
EOF

    # Append to
    arch="$(get_arch_from_chroot $chroot)"
    archs="$archs $arch"
    os="$(get_os_from_chroot $chroot)"
    oses="$oses $os"
    package_names="$package_names $package_name"
    error_causes="$error_causes $cause"

    # if  [ "$(grep -F '<!--error/'$cause' project/'$package' chroot/'$chroot'-->' $comment_body_file)" != "" ]; then
    #   >&2 echo "Comment body already contains entry for this cause/package/chroot combination. Continuing"
    #   continue;
    # fi

    # Wrap "more interesting" build log snippets in a <details open></details> block
    details_begin="<details>"
    if [ "$cause" == "unknown" ]; then
      # details_begin="<details open>"
      details_begin="<details>"
    fi

    build_log_entry="(see <a href=\"$build_log_url\">build log</a>)"
    if [ "$build_log_url" == "NOTFOUND" ]; then
      build_log_entry="(see <a href=\"$build_url\">build</a>)"
    fi

    heading=""
    if [ "$prev_cause" != "$cause" ]; then
      heading="</ol><h3>$cause</h3><ol>"
    fi
    prev_cause=$cause

    cat <<EOF >> $comment_body_file
$heading
<!--error/$cause project/$package_name chroot/$chroot-->
<li>
$details_begin
<summary>
<code>$package_name</code> on <code>$chroot</code> $build_log_entry [$(date --iso-8601=hours)]
</summary>

$(cat $context_file)

</details>
</li>
EOF
  done < $sorted_causes_file

  echo "</ol>" >> $comment_body_file

  if [ "$archs" != "" ]; then
    create_labels_for_archs $github_repo "$archs"
    create_labels_for_oses $github_repo "$oses"
    create_labels_for_projects $github_repo "$package_names"
    create_labels_for_error_causes $github_repo "$error_causes"

    os_labels=`for os in $oses; do echo -n " --add-label os/$os "; done`
    arch_labels=`for arch in $archs; do echo -n " --add-label arch/$arch " ; done`
    project_labels=`for project in $package_names; do echo -n " --add-label project/$project "; done`
    error_labels=`for cause in $error_causes; do echo -n " --add-label error/$cause "; done`

    gh --repo $github_repo \
      issue edit $issue_num \
      --body-file $comment_body_file $os_labels $arch_labels $project_labels $error_labels
  fi
  >&2 echo "Done updating issue comment for issue number $issue_num in $github_repo"
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

  >&2 echo "TODAY'S ISSUE IS $issue_number"

  >&2 echo "Begin handling error causes."

  # If no error causes file was passed, process build logs to get
  # error causes. Also ensure the error cause labels are created.
  if [[ -z "$causes_file" || ! -f "$causes_file" ]]; then
    causes_file=`mktemp`
    error_causes="`get_error_causes $copr_project_today $causes_file`"
    create_labels_for_error_causes $github_repo "$error_causes"
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
  local labels="$2"
  local label_prefix=$3
  local color=$4

  # Deduplicate labels
  for label in $(echo $labels | tr ' ' '\n' | sort | uniq | tr '\n' ' '); do
    local label_name=$label_prefix$label
    gh --repo $repo label create $label_name --color $color --force
  done

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
