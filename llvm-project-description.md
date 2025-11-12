We want to provide you with the most recent and successful builds of [LLVM](https://www.llvm.org) for Fedora and RHEL in a "rolling" fashion. That means, if you enable this repository, you should get new releases for LLVM frequently.

### Fedora versions and architectures

We build for the following architectures and operating systems, but please notice that this list changes when new Fedora/RHEL versions are being released.

```console
$ copr list-chroots | grep -P '^(fedora-(rawhide|[0-9]+)|rhel-[8,9]-)' | sort |  tr '\n' ' '
fedora-39-aarch64 fedora-39-i386 fedora-39-ppc64le fedora-39-s390x fedora-39-x86_64 fedora-40-aarch64 fedora-40-i386 fedora-40-ppc64le fedora-40-s390x fedora-40-x86_64 fedora-rawhide-aarch64 fedora-rawhide-i386 fedora-rawhide-ppc64le fedora-rawhide-s390x fedora-rawhide-x86_64 rhel-8-aarch64 rhel-8-s390x rhel-8-x86_64 rhel-9-aarch64 rhel-9-s390x
```

### Incubator projects

Did you notice a line like the follwing at the top of this project page?

```text
@fedora-llvm-team/llvm-snapshots ( forked from @fedora-llvm-team/llvm-snapshots-big-merge-20231218 )
```

We carefully create a new copr project for each day. These projects are called *incubator* projects.
Only if all packages for all operating systems and architectures in an incubator project were successfully built without errors,
we will promote it to be the next "official" snapshot here.

That is the reason why sometimes it can take days until a new version of LLVM
will be published here. If you're interested in the version for a particular day, feel free to open **https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots-big-merge-YYYYMMDD/** (replace **YYYYMMDD** with the date you desire). Notice, that we cannot keep the invdividual incubator projects around forever.

### Contributing

To get involved in this, please head over to: [https://github.com/fedora-llvm-team/llvm-snapshots](https://github.com/fedora-llvm-team/llvm-snapshots).
