%global compat_build 0

%global maj_ver 11
%global min_ver 1
%global patch_ver 0
%global rc_ver 2
%global baserelease 4

%global clang_tools_binaries \
	%{_bindir}/clang-apply-replacements \
	%{_bindir}/clang-change-namespace \
	%{_bindir}/clang-check \
	%{_bindir}/clang-doc \
	%{_bindir}/clang-extdef-mapping \
	%{_bindir}/clang-format \
	%{_bindir}/clang-include-fixer \
	%{_bindir}/clang-move \
	%{_bindir}/clang-offload-bundler \
	%{_bindir}/clang-offload-wrapper \
	%{_bindir}/clang-query \
	%{_bindir}/clang-refactor \
	%{_bindir}/clang-rename \
	%{_bindir}/clang-reorder-fields \
	%{_bindir}/clang-scan-deps \
	%{_bindir}/clang-tidy \
	%{_bindir}/clangd \
	%{_bindir}/diagtool \
	%{_bindir}/hmaptool \
	%{_bindir}/pp-trace

%global clang_binaries \
	%{_bindir}/clang \
	%{_bindir}/clang++ \
	%{_bindir}/clang-%{maj_ver} \
	%{_bindir}/clang++-%{maj_ver} \
	%{_bindir}/clang-cl \
	%{_bindir}/clang-cpp \

%if 0%{?compat_build}
%global pkg_name clang%{maj_ver}.%{min_ver}
# Install clang to same prefix as llvm, so that apps that use llvm-config
# will also be able to find clang libs.
%global install_prefix %{_libdir}/llvm%{maj_ver}.%{min_ver}
%global install_bindir %{install_prefix}/bin
%global install_includedir %{install_prefix}/include
%global install_libdir %{install_prefix}/lib

%global pkg_bindir %{install_bindir}
%global pkg_includedir %{_includedir}/llvm%{maj_ver}.%{min_ver}
%global pkg_libdir %{install_libdir}
%else
%global pkg_name clang
%global install_prefix /usr
%global pkg_libdir %{_libdir}
%endif

%if 0%{?fedora} || 0%{?rhel} > 7
%bcond_without python3
%else
%bcond_with python3
%endif

%global build_install_prefix %{buildroot}%{install_prefix}

%ifarch ppc64le
# Too many threads on ppc64 systems causes OOM errors.
%global _smp_mflags -j8
%endif

%global clang_srcdir clang-%{version}%{?rc_ver:rc%{rc_ver}}.src
%global clang_tools_srcdir clang-tools-extra-%{version}%{?rc_ver:rc%{rc_ver}}.src

Name:		%pkg_name
Version:	%{maj_ver}.%{min_ver}.%{patch_ver}
Release:	%{?rc_ver:0.}%{baserelease}%{?rc_ver:.rc%{rc_ver}}%{?dist}
Summary:	A C language family front-end for LLVM

License:	NCSA
URL:		http://llvm.org
Source0:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{clang_srcdir}.tar.xz
Source3:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{clang_srcdir}.tar.xz.sig
%if !0%{?compat_build}
Source1:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{clang_tools_srcdir}.tar.xz
Source2:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{clang_tools_srcdir}.tar.xz.sig
%endif
Source4:	tstellar-gpg-key.asc

Patch4:		0002-gtest-reorg.patch
Patch11:	0001-ToolChain-Add-lgcc_s-to-the-linker-flags-when-using-.patch
Patch13:	0001-Make-funwind-tables-the-default-for-all-archs.patch

# Not Upstream
Patch15:	0001-clang-Don-t-install-static-libraries.patch
Patch16:	0001-clang-Fix-spurious-test-failure.patch
Patch17:	0001-Driver-Prefer-gcc-toolchains-with-libgcc_s.so-when-n.patch

BuildRequires:	gcc
BuildRequires:	gcc-c++
BuildRequires:	cmake
BuildRequires:	ninja-build
%if 0%{?compat_build}
BuildRequires:	llvm%{maj_ver}.%{min_ver}-devel = %{version}
BuildRequires:	llvm%{maj_ver}.%{min_ver}-static = %{version}
%else
BuildRequires:	llvm-devel = %{version}
BuildRequires:	llvm-test = %{version}
# llvm-static is required, because clang-tablegen needs libLLVMTableGen, which
# is not included in libLLVM.so.
BuildRequires:	llvm-static = %{version}
BuildRequires:	llvm-googletest = %{version}
%endif

BuildRequires:	libxml2-devel
BuildRequires:	perl-generators
BuildRequires:	ncurses-devel
# According to https://fedoraproject.org/wiki/Packaging:Emacs a package
# should BuildRequires: emacs if it packages emacs integration files.
BuildRequires:	emacs

# These build dependencies are required for the test suite.
%if %with python3
# The testsuite uses /usr/bin/lit which is part of the python3-lit package.
BuildRequires:	python3-lit
%endif

BuildRequires:	python3-sphinx
BuildRequires:	libatomic

# We need python3-devel for pathfix.py.
BuildRequires:	python3-devel

# Needed for %%multilib_fix_c_header
BuildRequires:	multilib-rpm-config

# For origin certification
BuildRequires:	gnupg2

# scan-build uses these perl modules so they need to be installed in order
# to run the tests.
BuildRequires: perl(Digest::MD5)
BuildRequires: perl(File::Copy)
BuildRequires: perl(File::Find)
BuildRequires: perl(File::Path)
BuildRequires: perl(File::Temp)
BuildRequires: perl(FindBin)
BuildRequires: perl(Hash::Util)
BuildRequires: perl(lib)
BuildRequires: perl(Term::ANSIColor)
BuildRequires: perl(Text::ParseWords)
BuildRequires: perl(Sys::Hostname)

Requires:	%{name}-libs%{?_isa} = %{version}-%{release}

# clang requires gcc, clang++ requires libstdc++-devel
# - https://bugzilla.redhat.com/show_bug.cgi?id=1021645
# - https://bugzilla.redhat.com/show_bug.cgi?id=1158594
Requires:	libstdc++-devel
Requires:	gcc-c++

Provides:	clang(major) = %{maj_ver}

Conflicts:	compiler-rt < %{version}
Conflicts:	compiler-rt > %{version}

%description
clang: noun
    1. A loud, resonant, metallic sound.
    2. The strident call of a crane or goose.
    3. C-language family front-end toolkit.

The goal of the Clang project is to create a new C, C++, Objective C
and Objective C++ front-end for the LLVM compiler. Its tools are built
as libraries and designed to be loosely-coupled and extensible.

Install compiler-rt if you want the Blocks C language extension or to
enable sanitization and profiling options when building, and
libomp-devel to enable -fopenmp.

%package libs
Summary: Runtime library for clang
Requires: %{name}-resource-filesystem%{?_isa} = %{version}
Recommends: compiler-rt%{?_isa} = %{version}
# libomp-devel is required, so clang can find the omp.h header when compiling
# with -fopenmp.
Recommends: libomp-devel%{_isa} = %{version}
Recommends: libomp%{_isa} = %{version}

%description libs
Runtime library for clang.

%package devel
Summary: Development header files for clang
%if !0%{?compat_build}
Requires: %{name}%{?_isa} = %{version}-%{release}
# The clang CMake files reference tools from clang-tools-extra.
Requires: %{name}-tools-extra%{?_isa} = %{version}-%{release}
Requires: %{name}-libs = %{version}-%{release}
%endif

%description devel
Development header files for clang.

%package resource-filesystem
Summary: Filesystem package that owns the clang resource directory
Provides: %{name}-resource-filesystem(major) = %{maj_ver}

%description resource-filesystem
This package owns the clang resouce directory: $libdir/clang/$version/

%if !0%{?compat_build}
%package analyzer
Summary:	A source code analysis framework
License:	NCSA and MIT
BuildArch:	noarch
Requires:	%{name} = %{version}-%{release}

%description analyzer
The Clang Static Analyzer consists of both a source code analysis
framework and a standalone tool that finds bugs in C and Objective-C
programs. The standalone tool is invoked from the command-line, and is
intended to run in tandem with a build of a project or code base.

%package tools-extra
Summary:	Extra tools for clang
Requires:	%{name}-libs%{?_isa} = %{version}-%{release}
Requires:	emacs-filesystem

%description tools-extra
A set of extra tools built using Clang's tooling API.

# Put git-clang-format in its own package, because it Requires git
# and we don't want to force users to install all those dependenices if they
# just want clang.
%package -n git-clang-format
Summary:	Integration of clang-format for git
Requires:	%{name}-tools-extra = %{version}-%{release}
Requires:	git
Requires:	python3

%description -n git-clang-format
clang-format integration for git.


%package -n python3-clang
Summary:       Python3 bindings for clang
Requires:      %{name}-libs%{?_isa} = %{version}-%{release}
Requires:      python3
%description -n python3-clang
%{summary}.


%endif


%prep
%{gpgverify} --keyring='%{SOURCE4}' --signature='%{SOURCE3}' --data='%{SOURCE0}'

%if 0%{?compat_build}
%autosetup -n %{clang_srcdir} -p1
%else

%{gpgverify} --keyring='%{SOURCE4}' --signature='%{SOURCE2}' --data='%{SOURCE1}'
%setup -T -q -b 1 -n %{clang_tools_srcdir}


pathfix.py -i %{__python3} -pn \
	clang-tidy/tool/*.py \
	clang-include-fixer/find-all-symbols/tool/run-find-all-symbols.py

%setup -q -n %{clang_srcdir}

%patch4 -p1 -b .gtest
%patch11 -p1 -b .libcxx-fix
%patch13 -p2 -b .unwind-all
%patch15 -p2 -b .no-install-static
%patch16 -p2 -b .test-fix2
%patch17 -p1 -b .check-gcc_s

mv ../%{clang_tools_srcdir} tools/extra

pathfix.py -i %{__python3} -pn \
	tools/clang-format/*.py \
	tools/clang-format/git-clang-format \
	utils/hmaptool/hmaptool \
	tools/scan-view/bin/scan-view
%endif

%build

# We run the builders out of memory on armv7 and i686 when LTO is enabled
%ifarch %{arm} i686
%define _lto_cflags %{nil}
%else
# This package does not ship any object files or static libraries, so we
# don't need -ffat-lto-objects.
%global _lto_cflags %(echo %{_lto_cflags} | sed 's/-ffat-lto-objects//')
%endif

# lto builds with gcc 11 fail while running the lit tests.
%define _lto_cflags %{nil}

%if 0%{?__isa_bits} == 64
sed -i 's/\@FEDORA_LLVM_LIB_SUFFIX\@/64/g' test/lit.cfg.py
%else
sed -i 's/\@FEDORA_LLVM_LIB_SUFFIX\@//g' test/lit.cfg.py
%endif

%ifarch s390 s390x %{arm} %ix86 ppc64le
# Decrease debuginfo verbosity to reduce memory consumption during final library linking
%global optflags %(echo %{optflags} | sed 's/-g /-g1 /')
%endif

# -DCMAKE_INSTALL_RPATH=";" is a workaround for llvm manually setting the
# rpath of libraries and binaries.  llvm will skip the manual setting
# if CAMKE_INSTALL_RPATH is set to a value, but cmake interprets this value
# as nothing, so it sets the rpath to "" when installing.
%cmake  -G Ninja \
	-DLLVM_PARALLEL_LINK_JOBS=1 \
	-DLLVM_LINK_LLVM_DYLIB:BOOL=ON \
	-DCMAKE_BUILD_TYPE=RelWithDebInfo \
	-DPYTHON_EXECUTABLE=%{__python3} \
	-DCMAKE_INSTALL_RPATH:BOOL=";" \
%ifarch s390 s390x %{arm} %ix86 ppc64le
	-DCMAKE_C_FLAGS_RELWITHDEBINFO="%{optflags} -DNDEBUG" \
	-DCMAKE_CXX_FLAGS_RELWITHDEBINFO="%{optflags} -DNDEBUG" \
%endif
%if 0%{?compat_build}
	-DLLVM_CONFIG:FILEPATH=%{_bindir}/llvm-config-%{maj_ver}.%{min_ver}-%{__isa_bits} \
	-DCMAKE_INSTALL_PREFIX=%{install_prefix} \
	-DCLANG_INCLUDE_TESTS:BOOL=OFF \
%else
	-DCLANG_INCLUDE_TESTS:BOOL=ON \
	-DLLVM_EXTERNAL_LIT=%{_bindir}/lit \
	-DLLVM_MAIN_SRC_DIR=%{_datadir}/llvm/src \
%if 0%{?__isa_bits} == 64
	-DLLVM_LIBDIR_SUFFIX=64 \
%else
	-DLLVM_LIBDIR_SUFFIX= \
%endif
%endif
	\
%if !0%{compat_build}
	-DLLVM_TABLEGEN_EXE:FILEPATH=%{_bindir}/llvm-tblgen \
%else
	-DLLVM_TABLEGEN_EXE:FILEPATH=%{_bindir}/llvm-tblgen-%{maj_ver}.%{min_ver} \
%endif
	-DCLANG_ENABLE_ARCMT:BOOL=ON \
	-DCLANG_ENABLE_STATIC_ANALYZER:BOOL=ON \
	-DCLANG_INCLUDE_DOCS:BOOL=ON \
	-DCLANG_PLUGIN_SUPPORT:BOOL=ON \
	-DENABLE_LINKER_BUILD_ID:BOOL=ON \
	-DLLVM_ENABLE_EH=ON \
	-DLLVM_ENABLE_RTTI=ON \
	-DLLVM_BUILD_DOCS=ON \
	-DLLVM_ENABLE_SPHINX=ON \
	-DCLANG_LINK_CLANG_DYLIB=ON \
	-DSPHINX_WARNINGS_AS_ERRORS=OFF \
	\
	-DCLANG_BUILD_EXAMPLES:BOOL=OFF \
	-DBUILD_SHARED_LIBS=OFF \
	-DCLANG_REPOSITORY_STRING="%{?fedora:Fedora}%{?rhel:Red Hat} %{version}-%{release}"

%cmake_build

%install

%cmake_install

%if 0%{?compat_build}

# Remove binaries/other files
rm -Rf %{buildroot}%{install_bindir}
rm -Rf %{buildroot}%{install_prefix}/share
rm -Rf %{buildroot}%{install_prefix}/libexec

# Move include files
mkdir -p %{buildroot}%{pkg_includedir}
mv  %{buildroot}/%{install_includedir}/clang %{buildroot}/%{pkg_includedir}/
mv  %{buildroot}/%{install_includedir}/clang-c %{buildroot}/%{pkg_includedir}/

%else

# install clang python bindings
mkdir -p %{buildroot}%{python3_sitelib}/clang/
install -p -m644 bindings/python/clang/* %{buildroot}%{python3_sitelib}/clang/
%py_byte_compile %{__python3} %{buildroot}%{python3_sitelib}/clang

# multilib fix
%multilib_fix_c_header --file %{_includedir}/clang/Config/config.h

# Move emacs integration files to the correct directory
mkdir -p %{buildroot}%{_emacs_sitestartdir}
for f in clang-format.el clang-rename.el clang-include-fixer.el; do
mv %{buildroot}{%{_datadir}/clang,%{_emacs_sitestartdir}}/$f
done

# remove editor integrations (bbedit, sublime, emacs, vim)
rm -vf %{buildroot}%{_datadir}/clang/clang-format-bbedit.applescript
rm -vf %{buildroot}%{_datadir}/clang/clang-format-sublime.py*

# TODO: Package html docs
rm -Rvf %{buildroot}%{_docdir}/clang/html
rm -Rvf %{buildroot}%{_datadir}/clang/clang-doc-default-stylesheet.css
rm -Rvf %{buildroot}%{_datadir}/clang/index.js

# TODO: What are the Fedora guidelines for packaging bash autocomplete files?
rm -vf %{buildroot}%{_datadir}/clang/bash-autocomplete.sh

# Create Manpage symlinks
ln -s clang.1.gz %{buildroot}%{_mandir}/man1/clang++.1.gz
ln -s clang.1.gz %{buildroot}%{_mandir}/man1/clang-%{maj_ver}.1.gz
ln -s clang.1.gz %{buildroot}%{_mandir}/man1/clang++-%{maj_ver}.1.gz

# Add clang++-{version} symlink
ln -s clang++ %{buildroot}%{_bindir}/clang++-%{maj_ver}


# Fix permission
chmod u-x %{buildroot}%{_mandir}/man1/scan-build.1*

# create a link to clang's resource directory that is "constant" across minor
# version bumps
# this is required for packages like ccls that hardcode the link to clang's
# resource directory to not require rebuilds on minor version bumps
# Fix for bugs like rhbz#1807574
pushd %{buildroot}%{_libdir}/clang/
ln -s %{version} %{maj_ver}
popd

# Create sub-directories in the clang resource directory that will be
# populated by other packages
mkdir -p %{buildroot}%{_libdir}/clang/%{version}/{include,lib,share}/

%endif

# Remove clang-tidy headers.  We don't ship the libraries for these.
rm -Rvf %{buildroot}%{_includedir}/clang-tidy/

%check
%if !0%{?compat_build}
# requires lit.py from LLVM utilities
# FIXME: Fix failing ARM tests
LD_LIBRARY_PATH=%{buildroot}/%{_libdir} %cmake_build --target check-all || \
%ifarch %{arm}
:
%else
false
%endif

%endif


%if !0%{?compat_build}
%files
%license LICENSE.TXT
%{clang_binaries}
%{_mandir}/man1/clang.1.gz
%{_mandir}/man1/clang++.1.gz
%{_mandir}/man1/clang-%{maj_ver}.1.gz
%{_mandir}/man1/clang++-%{maj_ver}.1.gz
%endif

%files libs
%if !0%{?compat_build}
%{_libdir}/clang/
%{_libdir}/*.so.*
%else
%{pkg_libdir}/*.so.*
%{pkg_libdir}/clang/%{version}
%endif

%files devel
%if !0%{?compat_build}
%{_libdir}/*.so
%{_includedir}/clang/
%{_includedir}/clang-c/
%{_libdir}/cmake/*
%dir %{_datadir}/clang/
%else
%{pkg_libdir}/*.so
%{pkg_includedir}/clang/
%{pkg_includedir}/clang-c/
%{pkg_libdir}/cmake/
%endif

%files resource-filesystem
%dir %{pkg_libdir}/clang/%{version}/
%dir %{pkg_libdir}/clang/%{version}/include/
%dir %{pkg_libdir}/clang/%{version}/lib/
%dir %{pkg_libdir}/clang/%{version}/share/
%if !0%{?compat_build}
%{pkg_libdir}/clang/%{maj_ver}
%endif

%if !0%{?compat_build}
%files analyzer
%{_bindir}/scan-view
%{_bindir}/scan-build
%{_libexecdir}/ccc-analyzer
%{_libexecdir}/c++-analyzer
%{_datadir}/scan-view/
%{_datadir}/scan-build/
%{_mandir}/man1/scan-build.1.*

%files tools-extra
%{clang_tools_binaries}
%{_bindir}/c-index-test
%{_bindir}/find-all-symbols
%{_bindir}/modularize
%{_mandir}/man1/diagtool.1.gz
%{_emacs_sitestartdir}/clang-format.el
%{_emacs_sitestartdir}/clang-rename.el
%{_emacs_sitestartdir}/clang-include-fixer.el
%{_datadir}/clang/clang-format.py*
%{_datadir}/clang/clang-format-diff.py*
%{_datadir}/clang/clang-include-fixer.py*
%{_datadir}/clang/clang-tidy-diff.py*
%{_datadir}/clang/run-clang-tidy.py*
%{_datadir}/clang/run-find-all-symbols.py*
%{_datadir}/clang/clang-rename.py*

%files -n git-clang-format
%{_bindir}/git-clang-format

%files -n python3-clang
%{python3_sitelib}/clang/


%endif
%changelog
* Tue Jan 26 2021 Fedora Release Engineering <releng@fedoraproject.org> - 11.1.0-0.4.rc2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_34_Mass_Rebuild

* Fri Jan 22 2021 Serge Guelton - 11.1.0-0.3.rc2
- 11.1.0-rc2 release

* Wed Jan 20 2021 Serge Guelton - 11.1.0-0.2.rc1
- rebuilt with https://reviews.llvm.org/D94941 applied.

* Thu Jan 14 2021 Serge Guelton - 11.1.0-0.1.rc1
- 11.1.0-rc1 release

* Wed Jan 06 2021 Serge Guelton - 11.0.1-4
- LLVM 11.0.1 final

* Sun Dec 20 2020 sguelton@redhat.com - 11.0.1-3.rc2
- llvm 11.0.1-rc2

* Wed Dec 16 2020 Tom Stellard <tstellar@redhat.com> - 11.0.1-2.rc1
- Don't build with -flto

* Tue Dec 01 2020 sguelton@redhat.com - 11.0.1-1.rc1
- llvm 11.0.1-rc1

* Thu Oct 29 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-3
- Remove -ffat-lto-objects compiler flag

* Wed Oct 28 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-2
- Add clang-resource-filesystem sub-package

* Thu Oct 15 2020 sguelton@redhat.com - 11.0.0-1
- Fix NVR

* Mon Oct 12 2020 sguelton@redhat.com - 11.0.0-0.7
- llvm 11.0.0 - final release

* Thu Oct 08 2020 sguelton@redhat.com - 11.0.0-0.6.rc6
- 11.0.0-rc6

* Fri Oct 02 2020 sguelton@redhat.com - 11.0.0-0.5.rc5
- 11.0.0-rc5 Release

* Sun Sep 27 2020 sguelton@redhat.com - 11.0.0-0.4.rc3
- Fix NVR

* Thu Sep 24 2020 sguelton@redhat.com - 11.0.0-0.1.rc3
- 11.0.0-rc3 Release

* Tue Sep 22 2020 sguelton@redhat.com - 11.0.0-0.3.rc2
- Prefer gcc toolchains with libgcc_s

* Tue Sep 01 2020 sguelton@redhat.com - 11.0.0-0.2.rc2
- Normalize some doc directory locations

* Tue Sep 01 2020 sguelton@redhat.com - 11.0.0-0.1.rc2
- 11.0.0-rc2 Release
- Use %%license macro

* Tue Aug 11 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-0.2.rc1
- Fix test failures

* Mon Aug 10 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-0.1.rc1
- 11.0.0-rc1 Release

* Tue Aug 04 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-11
- Remove Requires: emacs-filesystem

* Sat Aug 01 2020 Fedora Release Engineering <releng@fedoraproject.org> - 10.0.0-10
- Second attempt - Rebuilt for
  https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Tue Jul 28 2020 Jeff Law <law@redhat.com> - 10.0.0-9
- Disable LTO on arm and i686

* Mon Jul 27 2020 Fedora Release Engineering <releng@fedoraproject.org> - 10.0.0-8
- Rebuilt for https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Mon Jul 20 2020 sguelton@redhat.com - 10.0.0-7
- Update cmake macro usage
- Finalize source verification

* Fri Jun 26 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-6
- Add cet.h header

* Mon Jun 08 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-5
- Accept multiple --config options

* Wed Jun  3 2020 Dan Čermák <dan.cermak@cgc-instruments.com> - 10.0.0-4
- Add symlink to %%{_libdir}/clang/%%{maj_ver} for persistent access to the resource directory accross minor version bumps

* Mon May 25 2020 Miro Hrončok <mhroncok@redhat.com> - 10.0.0-3
- Rebuilt for Python 3.9

* Tue May 19 2020 sguelton@redhat.com - 10.0.0-2
- Backport ad7211df6f257e39da2e5a11b2456b4488f32a1e, see rhbz#1825593

* Thu Mar 26 2020 sguelton@redhat.com - 10.0.0-1
- 10.0.0 final

* Tue Mar 24 2020 sguelton@redhat.com - 10.0.0-0.11.rc6
- 10.0.0 rc6

* Sun Mar 22 2020 sguelton@redhat.com - 10.0.0-0.10.rc5
- Update git-clang-format dependency, see rhbz#1815913

* Fri Mar 20 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-0.9.rc5
- Add dependency on libomp-devel

* Fri Mar 20 2020 sguelton@redhat.com - 10.0.0-0.8.rc5
- 10.0.0 rc5

* Sat Mar 14 2020 sguelton@redhat.com - 10.0.0-0.7.rc4
- 10.0.0 rc4

* Thu Mar 12 2020 sguelton@redhat.com - 10.0.0-0.6.rc3
- Move a few files from clang to clang-tools-extra.

* Thu Mar 05 2020 sguelton@redhat.com - 10.0.0-0.5.rc3
- 10.0.0 rc3

* Tue Feb 25 2020 sguelton@redhat.com - 10.0.0-0.4.rc2
- Apply -fdiscard-value-names patch.

* Mon Feb 17 2020 sguelton@redhat.com - 10.0.0-0.3.rc2
- Fix NVR

* Fri Feb 14 2020 sguelton@redhat.com - 10.0.0-0.1.rc2
- 10.0.0 rc2

* Tue Feb 11 2020 sguelton@redhat.com - 10.0.0-0.2.rc1
- Explicitly conflicts with any different compiler-rt version, see rhbz#1800705

* Fri Jan 31 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-0.1.rc1
- Stop shipping individual component libraries
- https://fedoraproject.org/wiki/Changes/Stop-Shipping-Individual-Component-Libraries-In-clang-lib-Package

* Fri Jan 31 2020 sguelton@redhat.com - 10.0.0-0.1.rc1
- 10.0.0 rc1

* Tue Jan 28 2020 Fedora Release Engineering <releng@fedoraproject.org> - 9.0.1-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_32_Mass_Rebuild

* Fri Jan 10 2020 Tom Stellard <tstellar@redhat.com> - 9.0.1-2
- Fix crash with kernel bpf self-tests

* Thu Dec 19 2019 Tom Stellard <tstellar@redhat.com> - 9.0.1-1
- 9.0.1 Release

* Wed Dec 11 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-3
- Add explicit requires for clang-libs to fix rpmdiff errors

* Tue Dec 10 2019 sguelton@redhat.com - 9.0.0-2
- Activate -funwind-tables on all arches, see rhbz#1655546.

* Thu Sep 19 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-1
- 9.0.0 Release

* Wed Sep 11 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-0.2.rc3
- Reduce debug info verbosity on ppc64le to avoid OOM errors in koji

* Thu Aug 22 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-0.1.rc3
- 9.0.0 Release candidate 3

* Tue Aug 20 2019 sguelton@redhat.com - 8.0.0-4
- Rebuilt for Python 3.8

* Mon Aug 19 2019 Miro Hrončok <mhroncok@redhat.com> - 8.0.0-3.2
- Rebuilt for Python 3.8

* Wed Jul 24 2019 Fedora Release Engineering <releng@fedoraproject.org> - 8.0.0-3.1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_31_Mass_Rebuild

* Thu May 16 2019 sguelton@redhat.com - 8.0.0-3
- Fix for rhbz#1674031

* Fri Apr 12 2019 sguelton@redhat.com - 8.0.0-2
- Remove useless patch thanks to GCC upgrade

* Wed Mar 20 2019 sguelton@redhat.com - 8.0.0-1
- 8.0.0 final

* Tue Mar 12 2019 sguelton@redhat.com - 8.0.0-0.6.rc4
- 8.0.0 Release candidate 4

* Mon Mar 4 2019 sguelton@redhat.com - 8.0.0-0.5.rc3
- Cleanup specfile after llvm dependency update

* Mon Mar 4 2019 sguelton@redhat.com - 8.0.0-0.4.rc3
- 8.0.0 Release candidate 3

* Mon Feb 25 2019 tstellar@redhat.com - 8.0.0-0.3.rc2
- Fix compiling with -stdlib=libc++

* Thu Feb 21 2019 sguelton@redhat.com - 8.0.0-0.2.rc2
- 8.0.0 Release candidate 2

* Sat Feb 09 2019 sguelton@redhat.com - 8.0.0-0.1.rc1
- 8.0.0 Release candidate 1

* Tue Feb 05 2019 sguelton@redhat.com - 7.0.1-6
- Update patch for Python3 port of scan-view

* Tue Feb 05 2019 sguelton@redhat.com - 7.0.1-5
- Working CI test suite

* Mon Feb 04 2019 sguelton@redhat.com - 7.0.1-4
- Workaround gcc-9 bug when compiling bitfields

* Fri Feb 01 2019 sguelton@redhat.com - 7.0.1-3
- Fix uninitialized error detected by gcc-9

* Thu Jan 31 2019 Fedora Release Engineering <releng@fedoraproject.org> - 7.0.1-2.1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_30_Mass_Rebuild

* Wed Dec 19 2018 Tom Stellard <tstellar@redhat.com> - 7.0.1-2
- Fix for rhbz#1657544

* Tue Dec 18 2018 sguelton@redhat.com - 7.0.1-1
- 7.0.1

* Tue Dec 18 2018 sguelton@redhat.com - 7.0.0-10
- Install proper manpage symlinks for clang/clang++ versions

* Fri Dec 14 2018 sguelton@redhat.com - 7.0.0-9
- No longer Ignore -fstack-clash-protection option

* Tue Dec 04 2018 sguelton@redhat.com - 7.0.0-8
- Ensure rpmlint passes on specfile

* Fri Nov 30 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-7
- Drop python2 dependency from clang-tools-extra

* Wed Nov 21 2018 sguelton@redhat.com - 7.0.0-6
- Prune unneeded reference to llvm-test-suite sub-package

* Mon Nov 19 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-5
- Run 'make check-all' instead of 'make check-clang'

* Mon Nov 19 2018 sergesanspaille <sguelton@redhat.com> - 7.0.0-4
- Avoid Python2 + Python3 dependency for clang-analyzer

* Mon Nov 05 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-3
- User helper macro to fixup config.h for multilib

* Tue Oct 02 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-2
- Use correct shebang substitution for python scripts

* Mon Sep 24 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-1
- 7.0.0 Release

* Wed Sep 19 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.16.rc3
- Move builtin headers into clang-libs sub-package

* Wed Sep 19 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.15.rc3
- Remove ambiguous python shebangs

* Thu Sep 13 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.14.rc3
- Move unversioned shared objects to devel package

* Thu Sep 13 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.13.rc3
- Rebuild with new llvm-devel that disables rpath on install

* Thu Sep 13 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.12.rc3
- Fix clang++-7 symlink

* Wed Sep 12 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.11.rc3
- 7.0.0-rc3 Release

* Mon Sep 10 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.10.rc2
- Drop siod from llvm-test-suite

* Fri Sep 07 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.9.rc2
- Drop python2 dependency from clang package

* Thu Sep 06 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.8.rc2
- Drop all uses of python2 from lit tests

* Sat Sep 01 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.7.rc2
- Add Fedora specific version string

* Tue Aug 28 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.6.rc2
- 7.0.0-rc2 Release

* Tue Aug 28 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.5.rc1
- Enable unit tests

* Fri Aug 17 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.4.rc1
- Move llvm-test-suite into a sub-package

* Fri Aug 17 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.3.rc1
- Recommend the same version of compiler-rt

* Wed Aug 15 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.2.rc1
- Rebuild for f30

* Mon Aug 13 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.1.rc1
- 7.0.0-rc1 Release

* Mon Jul 23 2018 Tom Stellard <tstellar@redhat.com> - 6.0.1-3
- Sync spec file with the clang6.0 package

* Thu Jul 12 2018 Fedora Release Engineering <releng@fedoraproject.org> - 6.0.1-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_29_Mass_Rebuild

* Tue Jun 26 2018 Tom Stellard <tstellar@redhat.com> - 6.0.1-1
- 6.0.1 Release

* Wed Jun 13 2018 Tom Stellard <tstellar@redhat.com> - 6.0.1-0.2.rc2
- 6.0.1-rc2

* Fri May 11 2018 Tom Stellard <tstellar@redhat.com> - 6.0.1-0.1.rc1
- 6.0.1-rc1 Release

* Fri Mar 23 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-5
- Add a clang++-{version} symlink rhbz#1534098

* Thu Mar 22 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-4
- Use correct script for running lit tests

* Wed Mar 21 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-3
- Fix toolchain detection so we don't default to using cross-compilers:
  rhbz#1482491

* Mon Mar 12 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-2
- Add Provides: clang(major) rhbz#1547444

* Fri Mar 09 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-1
- 6.0.0 Release

* Mon Feb 12 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.6.rc2
- 6.0.0-rc2 Release

* Wed Feb 07 2018 Fedora Release Engineering <releng@fedoraproject.org> - 6.0.0-0.5.rc1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_28_Mass_Rebuild

* Thu Feb 01 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.4.rc1
- Package python helper scripts for tools

* Fri Jan 26 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.3.rc1
- Ignore -fstack-clash-protection option instead of giving an error

* Fri Jan 26 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.2.rc1
- Package emacs integration files

* Wed Jan 24 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.1.rc1
- 6.0.0-rc1 Release

* Wed Jan 24 2018 Tom Stellard <tstellar@redhat.com> - 5.0.1-3
- Rebuild against llvm5.0 compatibility package
- rhbz#1538231

* Wed Jan 03 2018 Iryna Shcherbina <ishcherb@redhat.com> - 5.0.1-2
- Update Python 2 dependency declarations to new packaging standards
  (See https://fedoraproject.org/wiki/FinalizingFedoraSwitchtoPython3)

* Wed Dec 20 2017 Tom Stellard <tstellar@redhat.com> - 5.0.1-1
- 5.0.1 Release

* Wed Dec 13 2017 Tom Stellard <tstellar@redhat.com> - 5.0.0-3
- Make compiler-rt a weak dependency and add a weak dependency on libomp

* Mon Nov 06 2017 Merlin Mathesius <mmathesi@redhat.com> - 5.0.0-2
- Cleanup spec file conditionals

* Mon Oct 16 2017 Tom Stellard <tstellar@redhat.com> - 5.0.0-1
- 5.0.0 Release

* Wed Oct 04 2017 Rex Dieter <rdieter@fedoraproject.org> - 4.0.1-6
- python2-clang subpkg (#1490997)
- tools-extras: tighten (internal) -libs dep
- %%install: avoid cd

* Wed Aug 30 2017 Tom Stellard <tstellar@redhat.com> - 4.0.1-5
- Add Requires: python for git-clang-format

* Sun Aug 06 2017 Björn Esser <besser82@fedoraproject.org> - 4.0.1-4
- Rebuilt for AutoReq cmake-filesystem

* Wed Aug 02 2017 Fedora Release Engineering <releng@fedoraproject.org> - 4.0.1-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Binutils_Mass_Rebuild

* Wed Jul 26 2017 Fedora Release Engineering <releng@fedoraproject.org> - 4.0.1-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Fri Jun 23 2017 Tom Stellard <tstellar@redhat.com> - 4.0.1-1
- 4.0.1 Release.

* Fri Jun 16 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-8
- Enable make check-clang

* Mon Jun 12 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-7
- Package git-clang-format

* Thu Jun 08 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-6
- Generate man pages

* Thu Jun 08 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-5
- Ignore test-suite failures until all arches are fixed.

* Mon Apr 03 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-4
- Run llvm test-suite

* Mon Mar 27 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-3
- Enable eh/rtti, which are required by lldb.

* Fri Mar 24 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-2
- Fix clang-tools-extra build
- Fix install

* Thu Mar 23 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-1
- clang 4.0.0 final release

* Mon Mar 20 2017 David Goerger <david.goerger@yale.edu> - 3.9.1-3
- add clang-tools-extra rhbz#1328091

* Thu Mar 16 2017 Tom Stellard <tstellar@redhat.com> - 3.9.1-2
- Enable build-id by default rhbz#1432403

* Thu Mar 02 2017 Dave Airlie <airlied@redhat.com> - 3.9.1-1
- clang 3.9.1 final release

* Fri Feb 10 2017 Fedora Release Engineering <releng@fedoraproject.org> - 3.9.0-4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_26_Mass_Rebuild

* Mon Nov 14 2016 Nathaniel McCallum <npmccallum@redhat.com> - 3.9.0-3
- Add Requires: compiler-rt to clang-libs.
- Without this, compiling with certain CFLAGS breaks.

* Tue Nov  1 2016 Peter Robinson <pbrobinson@fedoraproject.org> 3.9.0-2
- Rebuild for new arches

* Fri Oct 14 2016 Dave Airlie <airlied@redhat.com> - 3.9.0-1
- clang 3.9.0 final release

* Fri Jul 01 2016 Stephan Bergmann <sbergman@redhat.com> - 3.8.0-2
- Resolves: rhbz#1282645 add GCC abi_tag support

* Thu Mar 10 2016 Dave Airlie <airlied@redhat.com> 3.8.0-1
- clang 3.8.0 final release

* Thu Mar 03 2016 Dave Airlie <airlied@redhat.com> 3.8.0-0.4
- clang 3.8.0rc3

* Wed Feb 24 2016 Dave Airlie <airlied@redhat.com> - 3.8.0-0.3
- package all libs into clang-libs.

* Wed Feb 24 2016 Dave Airlie <airlied@redhat.com> 3.8.0-0.2
- enable dynamic linking of clang against llvm

* Thu Feb 18 2016 Dave Airlie <airlied@redhat.com> - 3.8.0-0.1
- clang 3.8.0rc2

* Fri Feb 12 2016 Dave Airlie <airlied@redhat.com> 3.7.1-4
- rebuild against latest llvm packages
- add BuildRequires llvm-static

* Wed Feb 03 2016 Fedora Release Engineering <releng@fedoraproject.org> - 3.7.1-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_24_Mass_Rebuild

* Thu Jan 28 2016 Dave Airlie <airlied@redhat.com> 3.7.1-2
- just accept clang includes moving to /usr/lib64, upstream don't let much else happen

* Thu Jan 28 2016 Dave Airlie <airlied@redhat.com> 3.7.1-1
- initial build in Fedora.

* Tue Oct 06 2015 Jan Vcelak <jvcelak@fedoraproject.org> 3.7.0-100
- initial version using cmake build system
