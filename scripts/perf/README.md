# README

This container setup allows you to compare compile time performance of the
system llvm against "snapshot" (aka big-merge) and "pgo" for the current date.

# How to

Just run `make` to build and run the container image. Once that's done and
everything passed you should find a newly created `results` directory which
amonst others holds a `results.csv` file. This can be used for drawing
performance diagrams.
