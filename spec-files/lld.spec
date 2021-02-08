%global rc_ver 2
%global baserelease 3
%global lld_srcdir lld-%{version}%{?rc_ver:rc%{rc_ver}}.src
%global maj_ver 11
%global min_ver 1
%global patch_ver 0

# Don't include unittests in automatic generation of provides or requires.
%global __provides_exclude_from ^%{_libdir}/lld/.*$
%global __requires_exclude ^libgtest.*$

Name:		lld
Version:	%{maj_ver}.%{min_ver}.%{patch_ver}
Release:	%{?rc_ver:0.}%{baserelease}%{?rc_ver:.rc%{rc_ver}}%{?dist}
Summary:	The LLVM Linker

License:	NCSA
URL:		http://llvm.org
Source0:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{lld_srcdir}.tar.xz
Source1:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{lld_srcdir}.tar.xz.sig
Source2:	tstellar-gpg-key.asc
Source3:	run-lit-tests
Source4:	lit.lld-test.cfg.py

ExcludeArch:	s390x

Patch0:		0001-CMake-Check-for-gtest-headers-even-if-lit.py-is-not-.patch
Patch1:		0001-Revert-lld-Initial-commit-for-new-Mach-O-backend.patch

BuildRequires:	gcc
BuildRequires:	gcc-c++
BuildRequires:	cmake
BuildRequires:	ninja-build
BuildRequires:	llvm-devel = %{version}
BuildRequires:	llvm-test = %{version}
BuildRequires:	ncurses-devel
BuildRequires:	zlib-devel

# For make check:
BuildRequires:	python3-rpm-macros
BuildRequires:	python3-lit
BuildRequires:	llvm-googletest = %{version}

# For gpg source verification
BuildRequires:	gnupg2

Requires(post): %{_sbindir}/update-alternatives
Requires(preun): %{_sbindir}/update-alternatives

Requires: lld-libs = %{version}-%{release}

%description
The LLVM project linker.

%package devel
Summary:	Libraries and header files for LLD
Requires: lld-libs%{?_isa} = %{version}-%{release}
# lld tools are referenced in the cmake files, so we need to add lld as a
# dependency.
Requires: %{name}%{?_isa} = %{version}-%{release}

%description devel
This package contains library and header files needed to develop new native
programs that use the LLD infrastructure.

%package libs
Summary:	LLD shared libraries

%description libs
Shared libraries for LLD.

%package test
Summary: LLD regression tests
Requires:	%{name}%{?_isa} = %{version}-%{release}
Requires:	python3-lit
Requires:	llvm-test(major) = %{maj_ver}
Requires:	lld-libs = %{version}-%{release}

%description test
LLVM regression tests.

%prep
%{gpgverify} --keyring='%{SOURCE2}' --signature='%{SOURCE1}' --data='%{SOURCE0}'
%setup -q -n %{lld_srcdir}

%patch0 -p1 -b .gtest-fix
# Remove the MachO backend since it doesn't seem to work on big-endian hosts.
%ifarch s390x
%patch1 -p2 -b .remove-MachO
%endif


%build

# Disable lto since it causes the COFF/libpath.test lit test to crash.
%global _lto_cflags %{nil}

%cmake \
	-GNinja \
	-DLLVM_LINK_LLVM_DYLIB:BOOL=ON \
	-DLLVM_DYLIB_COMPONENTS="all" \
	-DCMAKE_SKIP_RPATH:BOOL=ON \
	-DPYTHON_EXECUTABLE=%{__python3} \
	-DLLVM_INCLUDE_TESTS=ON \
	-DLLVM_MAIN_SRC_DIR=%{_datadir}/llvm/src \
	-DLLVM_EXTERNAL_LIT=%{_bindir}/lit \
	-DLLVM_LIT_ARGS="-sv \
	--path %{_libdir}/llvm" \
%if 0%{?__isa_bits} == 64
	-DLLVM_LIBDIR_SUFFIX=64
%else
	-DLLVM_LIBDIR_SUFFIX=
%endif

%cmake_build

# Build the unittests so we can install them.
%cmake_build --target lld-test-depends

%install

%global lit_cfg test/%{_arch}.site.cfg.py
%global lit_unit_cfg test/Unit/%{_arch}.site.cfg.py
%global lit_lld_test_cfg_install_path %{_datadir}/lld/lit.lld-test.cfg.py

# Generate lit config files.  Strip off the last line that initiates the
# test run, so we can customize the configuration.
head -n -1 %{_target_platform}/test/lit.site.cfg.py >> %{lit_cfg}
head -n -1 %{_target_platform}/test/Unit/lit.site.cfg.py >> %{lit_unit_cfg}

# Patch lit config files to load custom config:
for f in %{lit_cfg} %{lit_unit_cfg}; do
  echo "lit_config.load_config(config, '%{lit_lld_test_cfg_install_path}')" >> $f
done

# Install test files
install -d %{buildroot}%{_datadir}/lld/src
cp %{SOURCE4} %{buildroot}%{_datadir}/lld/

# The various tar options are there to make sur the archive is the same on 32 and 64 bit arch, i.e.
# the archive creation is reproducible. Move arch-specific content out of the tarball
mv %{lit_cfg} %{buildroot}%{_datadir}/lld/src/%{_arch}.site.cfg.py
mv %{lit_unit_cfg} %{buildroot}%{_datadir}/lld/src/%{_arch}.Unit.site.cfg.py
tar --sort=name --mtime='UTC 2020-01-01' -c test/ | gzip -n > %{buildroot}%{_datadir}/lld/src/test.tar.gz

install -d %{buildroot}%{_libexecdir}/tests/lld
cp %{SOURCE3} %{buildroot}%{_libexecdir}/tests/lld

# Install unit test binaries
install -d %{buildroot}%{_libdir}/lld/
cp -R %{_target_platform}/unittests %{buildroot}%{_libdir}/lld/
rm -rf `find %{buildroot}%{_libdir}/lld/ -iname '*make*'`

# Install gtest libraries
cp %{_target_platform}/%{_lib}/libgtest*so* %{buildroot}%{_libdir}/lld/

# Install libraries and binaries
%cmake_install

# Required when using update-alternatives:
# https://docs.fedoraproject.org/en-US/packaging-guidelines/Alternatives/
touch %{buildroot}%{_bindir}/ld

%post
%{_sbindir}/update-alternatives --install %{_bindir}/ld ld %{_bindir}/ld.lld 1

%postun
if [ $1 -eq 0 ] ; then
  %{_sbindir}/update-alternatives --remove ld %{_bindir}/ld.lld
fi

%check

# armv7lhl tests disabled because of arm issue, see https://koji.fedoraproject.org/koji/taskinfo?taskID=33660162
%ifnarch %{arm}
%cmake_build --target check-lld
%endif

%ldconfig_scriptlets libs

%files
%license LICENSE.TXT
%ghost %{_bindir}/ld
%{_bindir}/lld*
%{_bindir}/ld.lld
%{_bindir}/ld64.lld
%{_bindir}/wasm-ld

%files devel
%{_includedir}/lld
%{_libdir}/liblld*.so
%{_libdir}/cmake/lld/

%files libs
%{_libdir}/liblld*.so.*

%files test
%{_libexecdir}/tests/lld/
%{_libdir}/lld/
%{_datadir}/lld/src/test.tar.gz
%{_datadir}/lld/src/%{_arch}.site.cfg.py
%{_datadir}/lld/src/%{_arch}.Unit.site.cfg.py
%{_datadir}/lld/lit.lld-test.cfg.py

%changelog
* Tue Jan 26 2021 Fedora Release Engineering <releng@fedoraproject.org> - 11.1.0-0.3.rc2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_34_Mass_Rebuild

* Fri Jan 22 2021 Serge Guelton - 11.1.0-0.2.rc2
- llvm 11.1.0-rc2 release

* Thu Jan 14 2021 Serge Guelton - 11.1.0-0.1.rc1
- 11.1.0-rc1 release

* Wed Jan 06 2021 Serge Guelton - 11.0.1-3
- LLVM 11.0.1 final

* Tue Dec 22 2020 sguelton@redhat.com - 11.0.1-2.rc2
- llvm 11.0.1-rc2

* Tue Dec 01 2020 sguelton@redhat.com - 11.0.1-1.rc1
- llvm 11.0.1-rc1

* Thu Nov 12 2020 sguelton@redhat.com - 11.0.0-3
- Exclude s390x, unsupported upstream

* Mon Oct 19 2020 sguelton@redhat.com - 11.0.0-2
- Rebuilt with all gating tests on

* Thu Oct 15 2020 sguelton@redhat.com - 11.0.0-1
- Fix NVR

* Mon Oct 12 2020 sguelton@redhat.com - 11.0.0-0.6
- llvm 11.0.0 - final release

* Thu Oct 08 2020 sguelton@redhat.com - 11.0.0-0.5.rc6
- 11.0.0-rc6

* Wed Oct 07 2020 sguelton@redhat.com - 11.0.0-0.4.rc5
- Update CI tests

* Fri Oct 02 2020 sguelton@redhat.com - 11.0.0-0.3.rc5
- 11.0.0-rc5 Release

* Sun Sep 27 2020 sguelton@redhat.com - 11.0.0-0.2.rc3
- Fix NVR

* Thu Sep 24 2020 sguelton@redhat.com - 11.0.0-0.1.rc3
- 11.0.0-rc3 Release

* Tue Sep 01 2020 sguelton@redhat.com - 11.0.0-0.1.rc2
- 11.0.0-rc2 Release

* Mon Aug 10 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-0.1.rc1
- 11.0.0-rc1 Release

* Mon Aug 10 2020 sguelton@redhat.com - 10.0.0-7
- use %%license macro

* Mon Aug 10 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-6
- Disable LTO

* Sat Aug 01 2020 Fedora Release Engineering <releng@fedoraproject.org> - 10.0.0-5
- Second attempt - Rebuilt for
  https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Tue Jul 28 2020 Fedora Release Engineering <releng@fedoraproject.org> - 10.0.0-4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Mon Jul 20 2020 sguelton@redhat.com - 10.0.0-3
- Use generic cmake macros
- Use Ninja as build system
- Remove chrpath dependency

* Fri Jul 17 2020 sguelton@redhat.com - 10.0.0-2
- Make test archive arch-independent

* Mon Mar 30 2020 sguelton@redhat.com - 10.0.0-1
- 10.0.0 final

* Wed Mar 25 2020 sguelton@redhat.com - 10.0.0-0.6.rc6
- 10.0.0 rc6

* Fri Mar 20 2020 sguelton@redhat.com - 10.0.0-0.5.rc5
- 10.0.0 rc5

* Sun Mar 15 2020 sguelton@redhat.com - 10.0.0-0.4.rc4
- 10.0.0 rc4

* Thu Mar 05 2020 sguelton@redhat.com - 10.0.0-0.3.rc3
- 10.0.0 rc3

* Fri Feb 14 2020 sguelton@redhat.com - 10.0.0-0.2.rc2
- 10.0.0 rc2

* Fri Jan 31 2020 sguelton@redhat.com - 10.0.0-0.1.rc1
- 10.0.0 rc1

* Wed Jan 29 2020 Fedora Release Engineering <releng@fedoraproject.org> - 9.0.1-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_32_Mass_Rebuild

* Thu Dec 19 2019 Tom Stellard <tstellar@redhat.com> -9.0.1-1
- 9.0.1 Release

* Sat Dec 14 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-6
- Fix some rpmdiff errors

* Fri Dec 13 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-5
- Remove build artifacts installed with unittests

* Thu Dec 05 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-4
- Enable GPG-based source file verification

* Thu Dec 05 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-3
- Add lld-test package

* Thu Nov 14 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-2
- Add explicit lld-libs requires to fix rpmdiff errors

* Thu Sep 19 2019 Tom Stellard <tstellar@redhat.com> -9.0.0-1
- 9.0.0 Release

* Thu Aug 22 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-0.1.rc3
- 9.0.0-rc3 Release

* Tue Aug 20 2019 Tom Stellard <tstellar@redhat.com> - 8.0.0-3
- touch /usr/bin/ld as required by the packaging guidelines for
  update-alternatives

* Tue Aug 13 2019 Tom Stellard <tstellar@redhat.com> - 8.0.0-2
- Add update-alternative for ld

* Thu Jul 25 2019 Fedora Release Engineering <releng@fedoraproject.org> - 8.0.0-1.1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_31_Mass_Rebuild

* Wed Mar 20 2019 sguelton@redhat.com - 8.0.0-1
- 8.0.0 final

* Tue Mar 12 2019 sguelton@redhat.com - 8.0.0-0.4.rc4
- 8.0.0 Release candidate 4

* Tue Mar 5 2019 sguelton@redhat.com - 8.0.0-0.4.rc3
- Cleanup specfile after llvm specfile update

* Mon Mar 4 2019 sguelton@redhat.com - 8.0.0-0.3.rc3
- 8.0.0 Release candidate 3

* Fri Feb 22 2019 sguelton@redhat.com - 8.0.0-0.2.rc2
- 8.0.0 Release candidate 2

* Mon Feb 11 2019 sguelton@redhat.com - 8.0.0-0.1.rc1
- 8.0.0 Release candidate 1

* Fri Feb 01 2019 Fedora Release Engineering <releng@fedoraproject.org> - 7.0.1-3.1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_30_Mass_Rebuild

* Mon Jan 14 2019 sguelton@redhat.com - 7.0.1-3
- Fix lld + annobin integration & Setup basic CI tests

* Mon Dec 17 2018 sguelton@redhat.com - 7.0.1-2
- Update lit dependency

* Mon Dec 17 2018 sguelton@redhat.com - 7.0.1-1
- 7.0.1 Release

* Tue Dec 04 2018 sguelton@redhat.com - 7.0.0-2
- Ensure rpmlint passes on specfile

* Mon Sep 24 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-1
- 7.0.1 Release

* Tue Sep 11 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.4.rc3
- 7.0.0-rc3 Release

* Fri Aug 31 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.3.rc2
- 7.0.0-rc2 Release

* Thu Aug 30 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.2.rc1
- Enable make check

* Mon Aug 13 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.1.rc1
- 7.0.0-rc1 Release

* Fri Jul 13 2018 Fedora Release Engineering <releng@fedoraproject.org> - 6.0.1-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_29_Mass_Rebuild

* Wed Jun 27 2018 Tom Stellard <tstellar@redhat.com> - 6.0.1-1
- 6.0.1 Release

* Fri May 11 2018 Tom Stellard <tstellar@redhat.com> - 6.0.1-0.1.rc1
- 6.0.1-rc1 Release

* Thu Mar 08 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-1
- 6.0.0 Release

* Tue Feb 13 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.3.rc2
- 6.0.0-rc2 Release

* Thu Feb 08 2018 Fedora Release Engineering <releng@fedoraproject.org> - 6.0.0-0.2.rc1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_28_Mass_Rebuild

* Thu Jan 25 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.1.rc1
- 6.0.0-rc1 Release

* Thu Dec 21 2017 Tom Stellard <tstellar@redhat.com> - 5.0.1-1
- 5.0.1 Release

* Mon Sep 11 2017 Tom Stellard <tstellar@redhat.com> - 5.0.0-1
- 5.0.0 Release

* Thu Aug 03 2017 Fedora Release Engineering <releng@fedoraproject.org> - 4.0.1-4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Binutils_Mass_Rebuild

* Wed Jul 26 2017 Fedora Release Engineering <releng@fedoraproject.org> - 4.0.1-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Thu Jul 06 2017 Tom Stellard <tstellar@redhat.com> - 4.0.1-2
- Backport r307092

* Tue Jul 04 2017 Tom Stellard <tstellar@redhat.com> - 4.0.1-1
- 4.0.1 Release

* Tue Jul 04 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-4
- Fix build without llvm-static

* Wed May 31 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-3
- Remove llvm-static dependency

* Mon May 15 2017 Fedora Release Engineering <rel-eng@lists.fedoraproject.org> - 4.0.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_26_27_Mass_Rebuild

* Tue Mar 14 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-1
- lld 4.0.0 Final Release
