# README

This container setup allows you to compare compile time performance of the
system llvm against "big-merge" (aka snapshot) and "pgo" for the current date.

# How to

Just run `make` to build and run the container image. It takes a long time to complete.

Then you'll be prompted with a markdown output that you can copy and paste into a github issue.

The output is located between `<!--BEGIN REPORT-->` and `<!--END REPORT-->` markers.
