Please, use this at your own risk!

For instructions on how to use this repository, consult the [official docs](https://docs.pagure.org/copr.copr/how_to_enable_repo.html#how-to-enable-repo).

In theory, this should be enough on a recent Fedora version:

```
$ dnf install 'dnf-command(copr)'
$ dnf copr enable @fedora-llvm-team/llvm-snapshots
```

Then install `clang` or some of the other packages.
Please note, that we keep the packages available here for a week or so.