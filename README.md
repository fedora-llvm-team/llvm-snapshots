# About

This project is home for the generation of daily

 * [LLVM source snapshots](https://github.com/kwk/llvm-daily-fedora-rpms/releases/tag/source-snapshot)
   * See [generate-snapshot-tarballs](https://github.com/kwk/llvm-daily-fedora-rpms/actions/workflows/generate-snapshot-tarballs.yml) workflow
 * [Fedora LLVM snapshot RPMs](https://copr.fedorainfracloud.org/coprs/g/fedora-llvm-team/llvm-snapshots/monitor/)
   * See [fedora-copr-build](https://github.com/kwk/llvm-daily-fedora-rpms/actions/workflows/fedora-copr-build.yml) workflow

## Troubleshooting

We also have a `Makefile` in case we encounter an error with the snapshots and
want to rebuild locally to fix errors. These are the make targets to choose from:

<dl>
<dt><code>clone-%</code></dt><dd>Clones the upstream-snapshot branch of the given package package (%) into the<br/>
 buildroot.</dd>
<dt><code>build-%</code></dt><dd>Clones and builds the package (%) and then installs it in the chroot.</dd>
<dt><code>init-mock</code></dt><dd>Initializes the mock chroot.</dd>
<dt><code>build-and-install-%</code></dt><dd>For the package (%) an SRPM and an RPM is built and then it is installed in<br/>
 the chroot.</dd>
<dt><code>shell</code></dt><dd>Opens up a shell to inspect the mock chroot.</dd>
<dt><code>install-vim</code></dt><dd>Allows you to use vim inside of mock.</dd>
<dt><code>clean-mock</code></dt><dd>Cleans the mock chroot</dd>
<dt><code>clean-buildroot</code></dt><dd>Removes the buildroot directory</dd>
<dt><code>clean</code></dt><dd>Cleans the mock chroot and removes the buildroot.</dd>
<dt><code>clean-%</code></dt><dd>Removes the buildroot dir for the given package (%).</dd>
<dt><code>copr-build-%</code></dt><dd>Builds the package (%) in copr by using the tooling used for the automated<br/>
 snapshot generation.</dd>
<dt><code>help</code></dt><dd>Display this help text.</dd>
<dt><code>help-html</code></dt><dd>Display this help text as an HTML definition list for better documentation generation</dd>
</dl>

### Usage

The LLVM snapshot packages depend on one another. The fastest and independent
package to build is `python-lit`. To try out how to build it, you can do:

```
make init-mock
make build-python-lit
```

This will initialize the mock environment. Note, that you only have to run this
once and not for every package. The second line clones the `upstream-snapshot`
branch of the `python-lit` package repository into
`./buildroot/<yyyymmdd>/python-lit` and starts a build of the package. We build
an SRPM, an RPM and then we install it. This makes the package available to the
next package to be built, e.g. `llvm`.

In case you encounter an error when build clang in the official snapshots, you
need `llvm` as a build dependency available in the mock environment. You're
options are to run `make build-llvm && make build-clang` or you could just run
`make build-clang`. Then the llvm version that is needed will be downloaded from
the official Fedora snapshot YUM repository (if it is available there).

