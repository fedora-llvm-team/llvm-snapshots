%global rc_ver 2
%global baserelease 3

%global crt_srcdir compiler-rt-%{version}%{?rc_ver:rc%{rc_ver}}.src

# see https://sourceware.org/bugzilla/show_bug.cgi?id=25271
%global optflags %(echo %{optflags} -D_DEFAULT_SOURCE)

# see https://gcc.gnu.org/bugzilla/show_bug.cgi?id=93615
%global optflags %(echo %{optflags} -Dasm=__asm__)

Name:		compiler-rt
Version:	11.1.0
Release:	%{?rc_ver:0.}%{baserelease}%{?rc_ver:.rc%{rc_ver}}%{?dist}
Summary:	LLVM "compiler-rt" runtime libraries

License:	NCSA or MIT
URL:		http://llvm.org
Source0:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{crt_srcdir}.tar.xz
Source1:	https://github.com/llvm/llvm-project/releases/download/llvmorg-%{version}%{?rc_ver:-rc%{rc_ver}}/%{crt_srcdir}.tar.xz.sig
Source2:	tstellar-gpg-key.asc

Patch0:		0001-PATCH-std-thread-copy.patch

BuildRequires:	gcc
BuildRequires:	gcc-c++
BuildRequires:	cmake
BuildRequires:	ninja-build
BuildRequires:	python3
# We need python3-devel for pathfix.py.
BuildRequires:	python3-devel
BuildRequires:	llvm-devel = %{version}

# For gpg source verification
BuildRequires:	gnupg2

Requires: clang-resource-filesystem%{?isa} = %{version}

%description
The compiler-rt project is a part of the LLVM project. It provides
implementation of the low-level target-specific hooks required by
code generation, sanitizer runtimes and profiling library for code
instrumentation, and Blocks C language extension.

%prep
%{gpgverify} --keyring='%{SOURCE2}' --signature='%{SOURCE1}' --data='%{SOURCE0}'
%autosetup -n %{crt_srcdir} -p1

pathfix.py -i %{__python3} -pn lib/hwasan/scripts/hwasan_symbolize

%build
%cmake  -GNinja \
	-DCMAKE_BUILD_TYPE=RelWithDebInfo \
	-DLLVM_CONFIG_PATH:FILEPATH=%{_bindir}/llvm-config-%{__isa_bits} \
	\
%if 0%{?__isa_bits} == 64
	-DLLVM_LIBDIR_SUFFIX=64 \
%else
	-DLLVM_LIBDIR_SUFFIX= \
%endif
	-DCOMPILER_RT_INCLUDE_TESTS:BOOL=OFF # could be on?

%cmake_build

%install

%cmake_install

# move blacklist/abilist files to where clang expect them
mkdir -p %{buildroot}%{_libdir}/clang/%{version}/share
mv -v %{buildroot}%{_datadir}/*list.txt  %{buildroot}%{_libdir}/clang/%{version}/share/

# move sanitizer libs to better place
%global libclang_rt_installdir lib/linux
mkdir -p %{buildroot}%{_libdir}/clang/%{version}/lib
mv -v %{buildroot}%{_prefix}/%{libclang_rt_installdir}/*clang_rt* %{buildroot}%{_libdir}/clang/%{version}/lib
mkdir -p %{buildroot}%{_libdir}/clang/%{version}/lib/linux/
pushd %{buildroot}%{_libdir}/clang/%{version}/lib
for i in *.a *.so
do
	ln -s ../$i linux/$i
done

# multilib support: also create symlink from lib to lib64, fixes rhbz#1678240
# the symlinks will be dangling if the 32 bits version is not installed, but that should be fine
%ifarch x86_64

mkdir -p %{buildroot}/%{_exec_prefix}/lib/clang/%{version}/lib/linux
for i in *.a *.so
do
	target=`echo "$i" | sed -e 's/x86_64/i386/'`
	ln -s ../../../../../lib/clang/%{version}/lib/$target ../../../../%{_lib}/clang/%{version}/lib/linux/
done
 
%endif
 
popd

%check

#%%cmake_build --target check-compiler-rt

%files
%license LICENSE.TXT
%{_includedir}/*
%{_libdir}/clang/%{version}/lib/*
%{_libdir}/clang/%{version}/share/*
%ifarch x86_64 aarch64
%{_bindir}/hwasan_symbolize
%endif

%changelog
* Tue Jan 26 2021 Fedora Release Engineering <releng@fedoraproject.org> - 11.1.0-0.3.rc2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_34_Mass_Rebuild

* Fri Jan 22 2021 Serge Guelton - 11.1.0-0.2.rc2
- 11.1.0-rc2 release

* Thu Jan 14 2021 Serge Guelton - 11.1.0-0.1.rc1
- 11.1.0-rc1 release

* Wed Jan 06 2021 Serge Guelton - 11.0.1-3
- LLVM 11.0.1 final

* Tue Dec 22 2020 sguelton@redhat.com - 11.0.1-2.rc2
- llvm 11.0.1-rc2

* Tue Dec 01 2020 sguelton@redhat.com - 11.0.1-1.rc1
- llvm 11.0.1-rc1

* Thu Oct 29 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-2
- Add dependency on clang-resource-filesystem

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

* Mon Aug 10 2020 Tom Stellard <tstellar@redhat.com> - 11.0.0-0.1.rc1
- 11.0.0-rc1 Release

* Wed Jul 29 2020 sguelton@redhat.com - 10.0.0-9
- use %%license macro

* Mon Jul 27 2020 sguelton@redhat.com - 10.0.0-8
- Remove now obsolete debuginfo package limitation

* Mon Jul 27 2020 Fedora Release Engineering <releng@fedoraproject.org> - 10.0.0-7
- Rebuilt for https://fedoraproject.org/wiki/Fedora_33_Mass_Rebuild

* Mon Jul 20 2020 sguelton@redhat.com - 10.0.0-6
- Use modern cmake macros

* Wed Jul 15 2020 sguelton@redhat.com - 10.0.0-5
- Fix multilib runtime links, see rhbz#1855379

* Wed Jul 15 2020 sguelton@redhat.com - 10.0.0-4
- Correctly use gpg verification

* Thu Jul 09 2020 Tom Stellard <tstellar@redhat.com> - 10.0.0-3
- Drop dependency on llvm-static

* Thu Jun 11 2020 sguelton@redhat.com - 10.0.0-2
- Fix msan compilation warnings, see af38074874c605f9 upstream

* Mon Mar 30 2020 sguelton@redhat.com - 10.0.0-1
- 10.0.0 final

* Wed Mar 25 2020 sguelton@redhat.com - 10.0.0-0.6.rc6
- 10.0.0 rc6

* Fri Mar 20 2020 sguelton@redhat.com - 10.0.0-0.5.rc5
- 10.0.0 rc5

* Sun Mar 15 2020 sguelton@redhat.com - 10.0.0-0.4.rc4
- 10.0.0 rc4

* Thu Mar 5 2020 sguelton@redhat.com - 10.0.0-0.3.rc3
- 10.0.0 rc3

* Fri Feb 14 2020 sguelton@redhat.com - 10.0.0-0.1.rc2
- 10.0.0 rc2

* Wed Feb 12 2020 sguelton@redhat.com - 10.0.0-0.2.rc1
- Ship blacklist files in the proper directory, see rhbz#1794936

* Fri Jan 31 2020 sguelton@redhat.com - 10.0.0-0.1.rc1
- 10.0.0 rc1

* Tue Jan 28 2020 Fedora Release Engineering <releng@fedoraproject.org> - 9.0.0-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_32_Mass_Rebuild

* Thu Sep 19 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-1
- 9.0.0 Release

* Thu Aug 22 2019 Tom Stellard <tstellar@redhat.com> - 9.0.0-0.1.rc3
- 9.0.0-rc3 Release

* Wed Jul 24 2019 Fedora Release Engineering <releng@fedoraproject.org> - 8.0.0-2.1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_31_Mass_Rebuild

* Tue Jun 18 2019 sguelton@redhat.com - 8.0.0-2
- Fix rhbz#1678240

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

* Thu Jan 31 2019 Fedora Release Engineering <releng@fedoraproject.org> - 7.0.1-2.1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_30_Mass_Rebuild

* Fri Jan 18 2019 sguelton@redhat.com - 7.0.1-2
- GCC-9 compatibility

* Mon Dec 17 2018 sguelton@redhat.com - 7.0.1-1
- 7.0.1 Release

* Tue Dec 04 2018 sguelton@redhat.com - 7.0.0-2
- Ensure rpmlint passes on specfile

* Mon Sep 24 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-1
- 7.0.0-1 Release

* Wed Sep 12 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.4.rc3
- 7.0.0-rc3 Release

* Fri Sep 07 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.3.rc1
- Use python3 for build scripts

* Thu Sep 06 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.2.rc1
- Drop BuildRequires: python2

* Tue Aug 14 2018 Tom Stellard <tstellar@redhat.com> - 7.0.0-0.1.rc1
- 7.0.0-rc1 Release

* Thu Jul 12 2018 Fedora Release Engineering <releng@fedoraproject.org> - 6.0.1-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_29_Mass_Rebuild

* Thu Jun 28 2018 Tom Stellard <tstellar@redhat.com> - 6.0.1-1
- 6.0.1 Release

* Mon Mar 19 2018 Iryna Shcherbina <ishcherb@redhat.com> - 6.0.0-2
- Update Python 2 dependency declarations to new packaging standards
  (See https://fedoraproject.org/wiki/FinalizingFedoraSwitchtoPython3)

* Thu Mar 08 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-1
- 6.0.0 Release

* Tue Feb 13 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.4.rc2
- 6.0.0-rc2 Release

* Tue Feb 13 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.3.rc1
- Fix build on AArch64

* Wed Feb 07 2018 Fedora Release Engineering <releng@fedoraproject.org> - 6.0.0-0.2.rc1
- Rebuilt for https://fedoraproject.org/wiki/Fedora_28_Mass_Rebuild

* Thu Jan 25 2018 Tom Stellard <tstellar@redhat.com> - 6.0.0-0.1.rc1
- 6.0.0-rc1 Release

* Wed Jan 17 2018 Tom Stellard <tstellar@redhat.com> - 5.0.1-2
- Build libFuzzer with gcc

* Wed Dec 20 2017 Tom Stellard <tstellar@redhat.com> - 5.0.1-1
- 5.0.1 Release

* Fri Oct 13 2017 Tom Stellard <tstellar@redhat.com> - 5.0.0-1
- 5.0.0 Release

* Mon Sep 25 2017 Tom Stellard <tstellar@redhat.com> - 4.0.1-6
- Fix AArch64 build with glibc 2.26

* Tue Sep 12 2017 Tom Stellard <tstellar@redhat.com> - 4.0.1-5
- Package libFuzzer

* Wed Aug 02 2017 Fedora Release Engineering <releng@fedoraproject.org> - 4.0.1-4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Binutils_Mass_Rebuild

* Wed Jul 26 2017 Fedora Release Engineering <releng@fedoraproject.org> - 4.0.1-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Fri Jun 23 2017 Tom Stellard <tstelar@redhat.com> - 4.0.1-2
- Fix build with newer glibc

* Fri Jun 23 2017 Tom Stellard <tstellar@redhat.com> - 4.0.1-1
- 4.0.1 Release

* Tue Mar 14 2017 Tom Stellard <tstellar@redhat.com> - 4.0.0-1
- compiler-rt 4.0.0 Final Release

* Thu Mar 02 2017 Dave Airlie <airlied@redhat.com> - 3.9.1-1
- compiler-rt 3.9.1

* Fri Feb 10 2017 Fedora Release Engineering <releng@fedoraproject.org> - 3.9.0-4
- Rebuilt for https://fedoraproject.org/wiki/Fedora_26_Mass_Rebuild

* Mon Nov 21 2016 Dan Horák <dan[at]danny.cz> - 3.9.0-3
- disable debuginfo on s390(x)

* Wed Nov 02 2016 Dave Airlie <airlied@redhat.com> - 3.9.0-2
- build for new arches.

* Wed Oct 26 2016 Dave Airlie <airlied@redhat.com> - 3.9.0-1
- compiler-rt 3.9.0 final release

* Mon May  2 2016 Tom Callaway <spot@fedoraproject.org> 3.8.0-2
- make symlinks to where the linker thinks these libs are

* Thu Mar 10 2016 Dave Airlie <airlied@redhat.com> 3.8.0-1
- compiler-rt 3.8.0 final release

* Thu Mar 03 2016 Dave Airlie <airlied@redhat.com> 3.8.0-0.2
- compiler-rt 3.8.0rc3

* Thu Feb 18 2016 Dave Airlie <airlied@redhat.com> - 3.8.0-0.1
- compiler-rt 3.8.0rc2

* Fri Feb 05 2016 Dave Airlie <airlied@redhat.com> 3.7.1-3
- fix compiler-rt paths - from rwindz0@gmail.com - #1304605

* Wed Feb 03 2016 Fedora Release Engineering <releng@fedoraproject.org> - 3.7.1-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_24_Mass_Rebuild

* Tue Oct 06 2015 Jan Vcelak <jvcelak@fedoraproject.org> 3.7.0-100
- initial version using cmake build system
