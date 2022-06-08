Name:       llvm-snapshot-builder
Version:    1.0.0
Release:    1
Summary:    A set of LUA functions used to build LLVM snaphots
License:    BSD
URL:        https://github.com/kwk/llvm-daily-fedora-rpms

Source0:    https://github.com/kwk/llvm-daily-fedora-rpms/blob/main/rpms/llvm-snapshot-builder/macros.llvm-snapshot-builder

%description
This package provides the llvm_sb macro which enables llvm_sb_xy() LUA functions
that are used for building LLVM snapshots.

Requires:   curl

%prep

%build

%install
install -p -m0644 -D %{SOURCE0} %{buildroot}%{_rpmmacrodir}/macros.%{name}

%files
%{_rpmmacrodir}/macros.%{name}

%changelog
* Wed Jun 08 2022 Konrad Kleine <kkleine@redhat.com> 1.0.1-3
- Show config during build

* Wed Jun 08 2022 Konrad Kleine <kkleine@redhat.com> 1.0.1-2
- Added old globals for convenience and added llvm_sb_debug, llvm_sb_version_tag

* Wed Jun 08 2022 Konrad Kleine <kkleine@redhat.com> 1.0.0-1
- initial version