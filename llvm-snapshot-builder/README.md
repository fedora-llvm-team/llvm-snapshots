# llvm-snapshot-builder

## About

The package "llvm-snaphot-builder" provides the `%{llvm_sb}` (sb=snapshot
builder) macro which unlocks llvm_sb_xy() LUA functions. Those are used when
building LLVM snapshots.

For legacy reasons this project also sets some RPM defines when the `%{llvm-sb}`
macro is called. Here's an example of how these defines can look like:

```
llvm_snapshot_version:            15.0.0
llvm_snapshot_version_tag:        15.0.0~pre20220608.g997ecb0036a56d
llvm_snapshot_version_major:      15
llvm_snapshot_version_minor:      0
llvm_snapshot_version_patch:      0
llvm_snapshot_yyyymmdd:           20220608
llvm_snapshot_git_revision:       997ecb0036a56df1fe77fafb69393255aa995de2
llvm_snapshot_git_revision_short: 997ecb0036a56d
llvm_snapshot_source_prefix:      https://github.com/kwk/llvm-daily-fedora-rpms/releases/download/source-snapshot/
llvm_snapshot_version_suffix:     pre20220608.g997ecb0036a56d
llvm_snapshot_changelog_entry:    * Wed Jun 08 2022 LLVM snapshot - 15.0.0~pre20220608.g997ecb0036a56d
```

## Who is this project for?

You don't need this project for *consuming* LLVM snapshots!

You only need to enable or install this project if you want to *build* LLVM snapshots.
