%global _binaries_in_noarch_packages_terminate_build %{nil}

%global rc_ver 2
%global baserelease 3
%global test_suite_srcdir test-suite-%{version}%{?rc_ver:rc%{rc_ver}}.src.fedora

Name:		llvm-test-suite
Version:	11.1.0
Release:	%{?rc_ver:0.}%{baserelease}%{?rc_ver:.rc%{rc_ver}}%{?dist}
Summary:	C/C++ Compiler Test Suite

License:	NCSA and BSD and GPLv1 and GPLv2+ and GPLv2 and MIT and Python and Public Domain and CRC32 and AML and Rdisc and ASL 2.0 and LGPLv3
URL:		http://llvm.org
# The LLVM Test Suite contains progrms with "BAD" or unknown licenses which should
# be removed.  Some of the unknown licenses may be OK, but until they are reviewed,
# we will remove them.
# Use the pkg_test_suite.sh script to generate the test-suite tarball:
# ./pkg_test_suite.sh

# this condition is set by ./pkg_test_suite.sh to retrieve original sources
%if 0%{?original_sources:1}
Source0:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/test-suite-%{version}%{?rc_ver:rc%{rc_ver}}.src.tar.xz
%else
Source0:	%{test_suite_srcdir}.tar.xz
%endif
Source1:	license-files.txt
Source2:	pkg_test_suite.sh
BuildArch:	noarch

Patch0: 0001-Fix-extra-Python3-print-statements.patch
Patch1: 0001-CLAMR-Fix-build-with-newer-glibc.patch

# We need python3-devel for pathfix.py.
BuildRequires: python3-devel

Requires: cmake
Requires: libstdc++-static
Requires: python3-lit >= 0.8.0
Requires: llvm
Requires: tcl
Requires: which

%description
C/C++ Compiler Test Suite that is maintained as an LLVM sub-project.  This test
suite can be run with any compiler, not just clang.


%prep
%autosetup -n %{test_suite_srcdir} -p1

pathfix.py -i %{__python3} -pn \
	ParseMultipleResults \
	utils/*.py \
	CollectDebugInfoUsingLLDB.py \
	CompareDebugInfo.py \
	tools/get-report-time \
	FindMissingLineNo.py \
	MicroBenchmarks/libs/benchmark-1.3.0/tools/compare_bench.py

chmod -R -x+X ABI-Testsuite

# Merge Licenses into a single file
cat %{SOURCE1} | while read FILE; do
	echo $FILE >> LICENSE.TXT
	cat ./$FILE >> LICENSE.TXT
done

%build

#nothing to do

%install
mkdir -p %{buildroot}%{_datadir}/llvm-test-suite/
cp -R %{_builddir}/%{test_suite_srcdir}/* %{buildroot}%{_datadir}/llvm-test-suite


%files
%license LICENSE.TXT
%{_datadir}/llvm-test-suite/


%changelog
* Tue Jan 26 2021 Fedora Release Engineering <releng@fedoraproject.org> - 11.1.0-0.3.rc2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_34_Mass_Rebuild

* Fri Jan 22 2021 Serge Guelton - 11.1.0-0.2.rc2
- llvm 11.1.0-rc2 release

* Thu Jan 14 2021 Serge Guelton - 11.1.0-0.1.rc1
- 11.1.0-rc1 release

* Wed Jan 06 2021 Serge Guelton - 11.0.1-3
- LLVM 11.0.1 final

* Mon Dec 21 2020 sguelton@redhat.com - 11.0.1-2.rc2
- llvm 11.0.1-rc2

* Tue Dec 01 2020 sguelton@redhat.com - 11.0.1-1.rc1
- llvm 11.0.1-rc1

* Thu Oct 15 2020 sguelton@redhat.com - 11.0.0-1
- Fix NVR

* Mon Oct 12 2020 sguelton@redhat.com - 11.0.0-0.5
- llvm 11.0.0 - final release

* Thu Oct 08 2020 sguelton@redhat.com - 11.0.0-0.4.rc6
- 11.0.0-rc6

* Fri Oct 02 2020 sguelton@redhat.com - 11.0.0-0.3.rc5
- 11.0.0-rc5 Release

* Sun Sep 27 2020 sguelton@redhat.com - 11.0.0-0.2.rc3
- Fix NVR

* Thu Sep 24 2020 sguelton@redhat.com - 11.0.0-0.1.rc3
- 11.0.0-rc3 Release

* Tue Sep 01 2020 sguelton@redhat.com - 11.0.0-0.1.rc2
- 11.0.0-rc2 Release

* Wed Aug 19 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-0.2.rc1
- Fix build failure with clang 11

* Mon Aug 10 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-0.1.rc1
- 11.0.0-rc1 Release

* Tue Jul 28 2020 Fedora Release Engineering <releng@fedoraproject.org> - 10.0.0-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Thu Jun 18 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-2
- Fix build with newer glibc

* Mon Mar 30 2020 sguelton@redhat.com - 10.0.0-1
- 10.0.0 final

* Tue Mar 24 2020 sguelton@redhat.com - 10.0.0-0.6.rc6
- 10.0.0 rc6

* Sat Mar 21 2020 sguelton@redhat.com - 10.0.0-0.5.rc5
- 10.0.0 rc5

* Sat Mar 14 2020 sguelton@redhat.com - 10.0.0-0.4.rc4
- 10.0.0 rc4

* Thu Mar 05 2020 sguelton@redhat.com - 10.0.0-0.3.rc3
- 10.0.0 rc3

* Fri Feb 14 2020 sguelton@redhat.com - 10.0.0-0.2.rc2
- 10.0.0 rc2

* Fri Jan 31 2020 sguelton@redhat.com - 10.0.0-0.1.rc1
- 10.0.0 rc1

* Wed Jan 29 2020 Fedora Release Engineering <releng@fedoraproject.org> - 9.0.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_32_Mass_Rebuild

* Fri Sep 20 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-1
- 9.0.0 Release

* Wed Sep 11 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-0.1.rc4
- 9.0.0-rc4 Release

* Thu Jul 25 2019 Fedora Release Engineering <releng@fedoraproject.org> - 8.0.0-3.1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_31_Mass_Rebuild

* Wed May 29 2019 Tom Stellard <tstellar@redhat.com> - 8.0.0-3
- Fix python2 print statement in ABI-Testsuite

* Thu May 02 2019 Tom Stellard <tstellar@redhat.com> - 8.0.0-2
- Bump lit version requirement

* Wed Mar 20 2019 sguelton@redhat.com - 8.0.0-1
- 8.0.0 final

* Tue Mar 12 2019 sguelton@redhat.com - 8.0.0-0.4.rc4
- 8.0.0 Release candidate 4

* Mon Mar 4 2019 sguelton@redhat.com - 8.0.0-0.3.rc3
- 8.0.0 Release candidate 3

* Fri Feb 22 2019 sguelton@redhat.com - 8.0.0-0.2.rc2
- 8.0.0 Release candidate 2

* Mon Feb 11 2019 sguelton@redhat.com - 8.0.0-0.1.rc1
- 8.0.0 Release candidate 1

* Mon Feb 04 2019 sguelton@redhat.com - 7.0.1-4
- Fix Python3 dependency

* Fri Feb 01 2019 Fedora Release Engineering <releng@fedoraproject.org> - 7.0.1-3.1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_30_Mass_Rebuild

* Fri Dec 21 2018 Miro Hrončok <mhroncok@redhat.com> - 7.0.1-3
- Remove Python2 dependency

* Fri Dec 21 2018 Tom Stellard <tstellar@redhat.com> - 7.0.1-2
- Bump version of lit dependency

* Mon Dec 17 2018 sguelton@redhat.com - 7.0.1-1
- 7.0.1 Release

* Fri Oct 26 2018 Tom Stellard <tstellar@redhat.com> - 7.0.1-0.1.rc2
- 7.0.1-rc2 Release
