%global rc_ver 1
%global baserelease 2
%global polly_srcdir polly-%{version}%{?rc_ver:rc%{rc_ver}}.src

Name: polly
Version: 11.1.0
Release: %{?rc_ver:0.}%{baserelease}%{?rc_ver:.rc%{rc_ver}}%{?dist}
Summary: LLVM Framework for High-Level Loop and Data-Locality Optimizations

License: NCSA
URL: http://polly.llvm.org
Source0: https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{polly_srcdir}.tar.xz
Source1: https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{polly_srcdir}.tar.xz.sig
Source2: tstellar-gpg-key.asc

Patch0: polly-subproject-extension.patch

BuildRequires: gcc
BuildRequires: gcc-c++
BuildRequires: cmake
BuildRequires: llvm-devel = %{version}
BuildRequires: llvm-test = %{version}
BuildRequires: clang-devel = %{version}
BuildRequires: ninja-build
BuildRequires: python3-lit
BuildRequires: python3-sphinx

# For origin certification
BuildRequires:	gnupg2

%description
Polly is a high-level loop and data-locality optimizer and optimization
infrastructure for LLVM. It uses an abstract mathematical representation based
on integer polyhedron to analyze and optimize the memory access pattern of a
program.

%package devel
Summary: Polly header files
Requires: %{name} = %{version}-%{release}

%description devel
Polly header files.

%package doc
Summary: Documentation for Polly
BuildArch: noarch
Requires: %{name} = %{version}-%{release}

%description doc
Documentation for the Polly optimizer.

%prep
%{gpgverify} --keyring='%{SOURCE2}' --signature='%{SOURCE1}' --data='%{SOURCE0}'
%autosetup -n %{polly_srcdir} -p1

%build

# LTO builds fail:
# ../lib/External/pet/include/pet.h:20:1: error: function 'pet_options_args' redeclared as variable
#   20 | ISL_ARG_DECL(pet_options, struct pet_options, pet_options_args)
#      | ^
#../lib/External/ppcg/external.c:107:6: note: previously declared here
#  107 | void pet_options_args() {
#     |      ^
%global _lto_cflags %{nil}

%cmake 	-GNinja \
	-DCMAKE_BUILD_TYPE=RelWithDebInfo \
	-DLLVM_LINK_LLVM_DYLIB:BOOL=ON \
	-DLLVM_EXTERNAL_LIT=%{_bindir}/lit \
	-DCMAKE_PREFIX_PATH=%{_libdir}/cmake/llvm/ \
\
	-DLLVM_ENABLE_SPHINX:BOOL=ON \
	-DSPHINX_WARNINGS_AS_ERRORS=OFF \
	-DSPHINX_EXECUTABLE=%{_bindir}/sphinx-build-3 \
\
%if 0%{?__isa_bits} == 64
	-DLLVM_LIBDIR_SUFFIX=64
%else
	-DLLVM_LIBDIR_SUFFIX=
%endif

%cmake_build
%cmake_build --target docs-polly-html


%install
%cmake_install

install -d %{buildroot}%{_pkgdocdir}/html
cp -r %{_vpath_builddir}/docs/html/* %{buildroot}%{_pkgdocdir}/html/

%check
%cmake_build --target check-polly

%files
%license LICENSE.txt
%{_libdir}/LLVMPolly.so
%{_libdir}/libPolly.so.*
%{_libdir}/libPollyISL.so
%{_libdir}/libPollyPPCG.so

%files devel
%{_libdir}/libPolly.so
%{_includedir}/polly
%{_libdir}/cmake/polly

%files doc
%doc %{_pkgdocdir}/html

%changelog
* Wed Jan 27 2021 Fedora Release Engineering <releng@fedoraproject.org> - 11.1.0-0.2.rc1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_34_Mass_Rebuild

* Thu Jan 14 2021 Serge Guelton - 11.1.0-0.1.rc1
- 11.1.0-rc1 release

* Wed Jan 06 2021 Serge Guelton - 11.0.1-3
- LLVM 11.0.1 final

* Tue Dec 22 2020 sguelton@redhat.com - 11.0.1-2.rc2
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

* Tue Aug 11 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-0.1.rc1
- 11.0.0-rc1 Release

* Tue Aug 11 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-6
- Disable LTO builds

* Mon Aug 10 2020 sguelton@redhat.com - 10.0.0-5
- Make gcc dependency explicit, see https://fedoraproject.org/wiki/Packaging:C_and_C%2B%2B#BuildRequires_and_Requires
- use %%license macro

* Sat Aug 01 2020 Fedora Release Engineering <releng@fedoraproject.org> - 10.0.0-4
- Second attempt - Rebuilt for
  https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Tue Jul 28 2020 Fedora Release Engineering <releng@fedoraproject.org> - 10.0.0-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Mon Jul 20 2020 sguelton@redhat.com - 10.0.0-2
- Modernize cmake macro usage

* Mon Mar 30 2020 sguelton@redhat.com - 10.0.0-1
- llvm-10.0.0 final

* Wed Mar 25 2020 sguelton@redhat.com - 10.0.0-0.2.rc6
- llvm-10.0.0 rc6

* Sat Mar 21 2020 sguelton@redhat.com - 10.0.0-0.1.rc5
- Initial version.

