For instructions on how to use this repository, consult the [official docs](https://docs.pagure.org/copr.copr/how_to_enable_repo.html#how-to-enable-repo).

You should be good to enable the copr repository and then install a package from it.

```
$ dnf -y install --skip-broken 'dnf-command(copr)' 'dnf5-command(copr)'
$ dnf -y copr enable @fedora-llvm-team/llvm-snapshots
```

Then install `clang` or some of the other packages.
