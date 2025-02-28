%include        %{_topdir}/SPECS/version.inc
Name:		weka-tools
Version:	%{_tools_version}
Release:	1%{?dist}
Summary:	WEKA Tools Collection
BuildArch:	x86_64

License:	GPL
URL:		https://weka.io

# unset __brp_mangle_shebangs - it chokes on ansible files.
%define __brp_mangle_shebangs /usr/bin/true


Requires:	coreutils
Requires:	tar
Requires:	findutils

# These all get installed in /opt/tools
Source0:	weka-tools.tgz

%define destdir	/opt/tools

%description
WEKA Tools Collection

%build
echo Good

%install
rm -rf $RPM_BUILD_ROOT

install -d -m 0755 %{buildroot}%{destdir}
tar xvf %{SOURCE0} -C %{buildroot}%{destdir}

%pre
# detach it from the git repo, if it exists
if [ -d %{destdir}/.git ]; then
	rm -rf %{destdir}/.git
fi

%files
%{destdir}/*

%changelog
* Thu Feb 13 2025 Vince Fleming <vince@weka.io>
-- 
