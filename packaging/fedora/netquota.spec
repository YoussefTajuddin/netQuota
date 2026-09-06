# UNTESTED skeleton: has not been run through `rpmbuild` yet.
# Build (from a source tree checked out as netquota-%{version}):
#   tar --transform 's,^,netquota-0.3.0/,' -czf ~/rpmbuild/SOURCES/netquota-0.3.0.tar.gz .
#   rpmbuild -bb packaging/fedora/netquota.spec

Name:           netquota
Version:        0.3.0
Release:        1%{?dist}
Summary:        Internet quota enforcement using nftables

License:        MIT
URL:            https://github.com/CHANGEME/netquota
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.10
Requires:       nftables
Requires:       vnstat
Requires:       iproute
Requires:       util-linux
Recommends:     firewalld
%{?systemd_requires}
BuildRequires:  systemd-rpm-macros

%description
NetQuota enforces a combined download+upload Internet quota on one network
interface using nftables (IPv4 and IPv6), with vnStat for display
statistics. The daemon runs as a dedicated unprivileged user with only
CAP_NET_ADMIN.

%prep
%setup -q

%build
# Pure Python + shell; nothing to compile.

%install
install -d %{buildroot}/usr/local/lib/netquota
cp -a netquota/. %{buildroot}/usr/local/lib/netquota/
find %{buildroot}/usr/local/lib/netquota -name '__pycache__' -exec rm -rf {} + || true
install -Dm755 packaging/common/netquota-wrapper %{buildroot}/usr/local/bin/netquota
install -Dm644 systemd/netquota.service %{buildroot}%{_unitdir}/netquota.service
install -Dm644 config/netquota.conf.example %{buildroot}%{_sysconfdir}/netquota.conf.example

%pre
getent passwd netquota >/dev/null || \
    useradd --system --no-create-home --shell /sbin/nologin netquota || :
exit 0

%post
install -d -o netquota -g netquota -m 0750 /var/lib/netquota
[ -f %{_sysconfdir}/netquota.conf ] || cp %{_sysconfdir}/netquota.conf.example %{_sysconfdir}/netquota.conf
%systemd_post netquota.service
echo "Next: sudo netquota setup   (then: sudo systemctl enable --now netquota.service)"

%preun
%systemd_preun netquota.service
nft delete table inet netquota 2>/dev/null || :

%postun
%systemd_postun_with_restart netquota.service
if [ $1 -eq 0 ]; then
    userdel netquota 2>/dev/null || :
fi

%files
/usr/local/lib/netquota
/usr/local/bin/netquota
%{_unitdir}/netquota.service
%config(noreplace) %{_sysconfdir}/netquota.conf.example

%changelog
* Sun Sep 06 2026 NetQuota Maintainers <noreply@example.invalid> - 0.3.0-1
- Initial Fedora packaging skeleton. See CHANGELOG.md for project history.
