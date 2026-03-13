// Package constants defines paths, table number ranges, naming conventions,
// and sysctl specifications used throughout sbr-config.
package constants

// System paths.
const (
	RTTablesPath    = "/etc/iproute2/rt_tables"
	BackupDir       = "/var/lib/sbr-config/backups"
	LogFileDefault  = "/var/log/sbr-config.log"
	LockFile        = "/var/run/sbr-config.lock"
	SysctlConfPath  = "/etc/sysctl.d/90-sbr-config.conf"
)

// Routing table allocation.
const (
	TableNamePrefix  = "sbr_"
	TableNumberStart = 100
	TableNumberMax   = 250 // Stay below 253 (default), 254 (main), 255 (local)
)

// IP rule priority allocation.
const (
	RulePriorityStart     = 100
	RulePriorityIncrement = 10
)

// ReservedTableNumbers must never be allocated.
var ReservedTableNumbers = map[int]bool{
	0: true, 253: true, 254: true, 255: true,
}

// ReservedTableNames must never be allocated.
var ReservedTableNames = map[string]bool{
	"unspec": true, "default": true, "main": true, "local": true,
}

// NetworkManager paths.
const (
	NMDispatcherDir    = "/etc/NetworkManager/dispatcher.d"
	NMDispatcherScript = "50-sbr-config"
)

// systemd-networkd paths.
const SystemdNetworkDir = "/etc/systemd/network"

// Netplan paths.
const (
	NetplanDir        = "/etc/netplan"
	NetplanConfigFile = "90-sbr-config.yaml"
)

// ifupdown paths.
const (
	InterfacesFile = "/etc/network/interfaces"
	InterfacesDDir = "/etc/network/interfaces.d"
)

// ManagedComment is written into every file sbr-config manages so we
// can identify (and safely remove) our own files later.
const ManagedComment = "# Managed by sbr-config -- do not edit manually"

// DHCPLeasePaths is the search order for DHCP lease files.
// The placeholder {iface} is replaced at runtime.
var DHCPLeasePaths = []string{
	"/var/lib/dhclient/dhclient-{iface}.leases",
	"/var/lib/dhclient/dhclient-{iface}.lease",
	"/var/lib/dhcp/dhclient.{iface}.leases",
	"/var/lib/dhcp/dhclient.{iface}.lease",
	"/var/lib/dhcp/dhclient-{iface}.leases",
	"/var/lib/NetworkManager/dhclient-*-{iface}.lease",
	"/var/lib/NetworkManager/internal-*-{iface}.lease",
	"/run/systemd/netif/leases/*",
}

// SysctlSpec describes one required sysctl parameter.
type SysctlSpec struct {
	Required    string
	Description string
	Reason      string
}

// SysctlSettings maps sysctl key → spec for global settings.
var SysctlSettings = map[string]SysctlSpec{
	"net.ipv4.conf.all.rp_filter": {
		Required:    "2",
		Description: "Reverse path filtering (loose mode)",
		Reason: "Strict mode (1) drops packets arriving on an interface that isn't the " +
			"best reverse path per the main routing table. Loose mode (2) accepts " +
			"packets as long as any route to the source exists, which is necessary " +
			"when custom SBR tables provide the return path.",
	},
	"net.ipv4.conf.default.rp_filter": {
		Required:    "2",
		Description: "Reverse path filtering for new interfaces (loose mode)",
		Reason: "Sets the default rp_filter for newly created interfaces. Must be loose (2) " +
			"to ensure new interfaces work correctly with source-based routing.",
	},
	"net.ipv4.conf.all.arp_filter": {
		Required:    "1",
		Description: "ARP filtering (enabled)",
		Reason: "When enabled, the kernel only responds to ARP requests on the interface " +
			"whose address matches the request. This prevents ARP flux on multi-NIC " +
			"systems where multiple interfaces could respond to the same ARP query.",
	},
	"net.ipv4.conf.all.arp_announce": {
		Required:    "2",
		Description: "ARP announcement (use best local address)",
		Reason: "Value 2 tells the kernel to always use the best local address for the " +
			"target subnet when sending ARP requests. This prevents ARP confusion " +
			"when multiple interfaces are present.",
	},
}

// SysctlSettingsOrder defines the iteration order for global sysctl settings,
// matching the Python implementation's output order for file compatibility.
var SysctlSettingsOrder = []string{
	"net.ipv4.conf.all.rp_filter",
	"net.ipv4.conf.default.rp_filter",
	"net.ipv4.conf.all.arp_filter",
	"net.ipv4.conf.all.arp_announce",
}

// SysctlPerIfaceTemplate is the per-interface rp_filter key template.
// Replace {iface} with the interface name at runtime.
const SysctlPerIfaceTemplate = "net.ipv4.conf.{iface}.rp_filter"
