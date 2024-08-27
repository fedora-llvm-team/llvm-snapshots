For instructions on how to use this repository, consult the [official docs](https://docs.pagure.org/copr.copr/how_to_enable_repo.html#how-to-enable-repo).

We need a bit of post-configuration after enabling the copr repository for this project:

```
$ dnf install -y jq envsubst 'dnf-command(copr)'
$ dnf copr enable -y @fedora-llvm-team/llvm-snapshots
$ repo_file=$(dnf repoinfo --json *llvm-snapshots* | jq -r ".[0].repo_file_path")
$ distname=$(rpm --eval "%{?fedora:fedora}%{?rhel:rhel}") envsubst '$distname' < $repo_file > /tmp/new_repo_file
$ cat /tmp/new_repo_file > $repo_file
```

Then install `clang` or some of the other packages.
