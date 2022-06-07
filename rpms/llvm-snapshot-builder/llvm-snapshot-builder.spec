Name:       llvm-snapshot-builder
Version:    1.0.0
Release:    1
Summary:    A set of LUA functions used to build LLVM snaphots
License:    BSD
URL:        https://github.com/kwk/llvm-daily-fedora-rpms

%description
This package provides the llvm_sb macro which enables llvm_sb_xy() functions
that are used for building LLVM snapshots.

Source0: macros.llvm-snapshot-builder

%prep
%build

%install
mkdir -p %{buildroot}/usr/bin/
install -p -m0644 -D %{SOURCE0} %{buildroot}%{_rpmmacrodir}/macros.%{name}

%files
%{_rpmmacrodir}/macros.%{name}

%changelog
* Tue Jun 08 2022 Konrad Kleine <kkleine@redhat.com> 1.0.0-1
- initial version