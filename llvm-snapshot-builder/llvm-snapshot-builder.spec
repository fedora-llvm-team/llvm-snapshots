Name:       llvm-snapshot-builder
Version:    1.2.9
Release:    1%{?dist}
Summary:    A set of LUA functions used to build LLVM snaphots
License:    BSD
URL:        https://pagure.io/llvm-snapshot-builder
Source0:    llvm-snapshot-builder-1.2.9.tar.bz2
BuildArch:  noarch
Requires:   curl

%description
This package provides the llvm_sb macro for LLVM snaphot building.

%prep
%autosetup -n llvm-snapshot-builder

%build

%install
install -p -m0644 -D macros.%{name} %{buildroot}%{_rpmmacrodir}/macros.%{name}

%files
%{_rpmmacrodir}/macros.%{name}

%changelog
* Tue Feb 21 2023 Konrad Kleine <kkleine@redhat.com> - 1.2.9-1
- Initial Release
