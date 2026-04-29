"""Paths, table number ranges, naming conventions, and other constants."""

# System paths
RT_TABLES_PATH = "/etc/iproute2/rt_tables"
BACKUP_DIR = "/var/lib/sbr-config/backups"
LOG_FILE_DEFAULT = "/var/log/sbr-config.log"
LOCK_FILE = "/var/run/sbr-config.lock"
SYSCTL_CONF_PATH = "/etc/sysctl.d/90-sbr-config.conf"

# Routing table allocation
TABLE_NAME_PREFIX = "sbr_"
TABLE_NUMBER_START = 100
TABLE_NUMBER_MAX = 250  # Stay below 253 (default), 254 (main), 255 (local)

# IP rule priority allocation
RULE_PRIORITY_START = 100
RULE_PRIORITY_INCREMENT = 10

# Reserved routing table numbers (never allocate these)
RESERVED_TABLE_NUMBERS = {0, 253, 254, 255}
RESERVED_TABLE_NAMES = {"unspec", "default", "main", "local"}

# NetworkManager
NM_DISPATCHER_DIR = "/etc/NetworkManager/dispatcher.d"
NM_DISPATCHER_SCRIPT = "50-sbr-config"

# systemd-networkd
SYSTEMD_NETWORK_DIR = "/etc/systemd/network"

# Netplan
NETPLAN_DIR = "/etc/netplan"
NETPLAN_CONFIG_FILE = "90-sbr-config.yaml"

# ifupdown
INTERFACES_FILE = "/etc/network/interfaces"
INTERFACES_D_DIR = "/etc/network/interfaces.d"

# Marker comment for managed files
MANAGED_COMMENT = "# Managed by sbr-config -- do not edit manually"

# DHCP lease file search paths
DHCP_LEASE_PATHS = [
    "/var/lib/dhclient/dhclient-{iface}.leases",
    "/var/lib/dhclient/dhclient-{iface}.lease",
    "/var/lib/dhcp/dhclient.{iface}.leases",
    "/var/lib/dhcp/dhclient.{iface}.lease",
    "/var/lib/dhcp/dhclient-{iface}.leases",
    "/var/lib/NetworkManager/dhclient-*-{iface}.lease",
    "/var/lib/NetworkManager/internal-*-{iface}.lease",
    "/run/systemd/netif/leases/*",
]

# Sysctl settings required for SBR
SYSCTL_SETTINGS = {
    "net.ipv4.conf.all.rp_filter": {
        "required": "2",
        "description": "Reverse path filtering (loose mode)",
        "reason": (
            "Strict mode (1) drops packets arriving on an interface that isn't the "
            "best reverse path per the main routing table. Loose mode (2) accepts "
            "packets as long as any route to the source exists, which is necessary "
            "when custom SBR tables provide the return path."
        ),
    },
    "net.ipv4.conf.default.rp_filter": {
        "required": "2",
        "description": "Reverse path filtering for new interfaces (loose mode)",
        "reason": (
            "Sets the default rp_filter for newly created interfaces. Must be loose (2) "
            "to ensure new interfaces work correctly with source-based routing."
        ),
    },
    "net.ipv4.conf.all.arp_filter": {
        "required": "1",
        "description": "ARP filtering (enabled)",
        "reason": (
            "When enabled, the kernel only responds to ARP requests on the interface "
            "whose address matches the request. This prevents ARP flux on multi-NIC "
            "systems where multiple interfaces could respond to the same ARP query."
        ),
    },
    "net.ipv4.conf.default.arp_filter": {
        "required": "1",
        "description": "ARP filtering for new interfaces (enabled)",
        "reason": (
            "Sets the default arp_filter for newly created interfaces so that any "
            "NIC brought up after sbr-config runs inherits the same per-interface "
            "ARP behavior."
        ),
    },
    "net.ipv4.conf.all.arp_announce": {
        "required": "2",
        "description": "ARP announcement (use best local address)",
        "reason": (
            "Value 2 tells the kernel to always use the best local address for the "
            "target subnet when sending ARP requests. This prevents ARP confusion "
            "when multiple interfaces are present."
        ),
    },
    "net.ipv4.conf.default.arp_announce": {
        "required": "2",
        "description": "ARP announcement for new interfaces (use best local address)",
        "reason": (
            "Sets the default arp_announce for newly created interfaces so that any "
            "NIC brought up after sbr-config runs inherits the same outgoing ARP "
            "source-selection behavior."
        ),
    },
    "net.ipv4.conf.all.arp_ignore": {
        "required": "1",
        "description": "ARP ignore (reply only on matching interface)",
        "reason": (
            "Value 1 tells the kernel to reply to an ARP request only if the target "
            "IP is configured on the receiving interface. Required when multiple "
            "NICs share a broadcast domain (common for WEKA frontends with several "
            "NICs on the same subnet) to prevent ARP flux, where one NIC answers "
            "for an IP that lives on another."
        ),
    },
    "net.ipv4.conf.default.arp_ignore": {
        "required": "1",
        "description": "ARP ignore for new interfaces (reply only on matching interface)",
        "reason": (
            "Sets the default arp_ignore for newly created interfaces so that any "
            "NIC brought up after sbr-config runs inherits the same anti-ARP-flux "
            "behavior."
        ),
    },
}

# Per-interface sysctl template (rp_filter must be set per-iface too)
SYSCTL_PER_IFACE_TEMPLATE = "net.ipv4.conf.{iface}.rp_filter"
