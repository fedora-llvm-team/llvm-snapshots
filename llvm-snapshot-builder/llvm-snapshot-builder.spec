Name:       llvm-snapshot-builder
Release:    1%{?dist}
Summary:    A set of LUA functions used to build LLVM snaphots
License:    BSD
URL:        https://pagure.io/llvm-snapshot-builder
Source0:    %{name}-%{version}.tar.bz2
BuildArch:  noarch
Requires:   curl

%description
This package provides the llvm_sb macro for LLVM snaphot building.

%prep
%autosetup -n %{name}

%build

%install
install -p -m0644 -D macros.%{name} %{buildroot}%{_rpmmacrodir}/macros.%{name}

%files
%{_rpmmacrodir}/macros.%{name}

%changelog
* %{lua: print(os.date("%a %b %d %Y"))} LLVM snapshot - %{version}
- This is an automated snapshot build

* Thu Feb 23 2023 Konrad Kleine <kkleine@redhat.com> - 3.0.0-1
- Bump version to be newer than what's currently in Copr @fedora-llvm-team/llvm-snapshot-builder

* Tue Feb 21 2023 Konrad Kleine <kkleine@redhat.com> - 1.2.9-1
- Initial Release
