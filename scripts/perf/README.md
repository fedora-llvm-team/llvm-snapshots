# README

This container setup allows you to compare compile time performance of the
system llvm against "snapshot" (aka big-merge) and "pgo" for the current date.

# How to

Just run `make` to build and run the container image. Once that's done and
everything passed you should find a newly created `results` directory which
holds these files:

```
   1. pgo.json
   2. snapshot.json
   3. system.json
   4. pgo_vs_snapshot.compile_time.txt
   5. pgo_vs_system.compile_time.txt
   6. snapshot_vs_system.compile_time.txt
   7. result.csv
   8. report.md
```

The `report.md` is something you can copy and paste into a github issue comment.
