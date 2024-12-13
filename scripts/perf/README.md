# README

This container setup allows you to compare the system llvm against "big-merge" and "pgo".

# How to

Just run `make` to build and run the container image. It takes a long time to complete.

Then you'll be promted to a terminal in the container where you'll find these files:

```
~/results-system-vs-pgo.txt
~/results-system-vs-big-merge.txt
~/results-big-merge-vs-pgo.txt
```

The names speak for themselves.

## How to change to OS

If you want to change the version of the operating system, go to `Containerfile` and change the line that looks like this: `FROM fedora:40`. Change it to `FROM fedora:41` or something else.

Then run `make` again.

## How to change the date for which to compare results?

Go to `entrypoint.sh` and change the line that defines `yyyymmdd` to the year-month-date of your liking.
