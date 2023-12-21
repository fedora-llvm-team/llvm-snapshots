For instructions on how to use this repository, consult the [official docs](https://docs.pagure.org/copr.copr/how_to_enable_repo.html#how-to-enable-repo).

It should be enough to enable the copr repository for this project using the following command:

```
$ dnf install 'dnf-command(copr)'
$ dnf copr enable -y @fedora-llvm-team/llvm-snapshots
```

Then install `clang` or some of the other packages.
