# SBR-Config

**Linux Source-Based Routing Configuration Tool**

Automatically detect, validate, and configure source-based routing (policy routing) for multi-NIC Linux systems. Ensures traffic leaves through the same interface it arrived on, preventing asymmetric routing and dropped connections.

## The Problem

On a Linux system with multiple network interfaces, the kernel uses the main routing table for all outbound traffic by default. This means responses to connections arriving on a secondary interface often exit through the primary interface (the one with the default route), causing:

- **Asymmetric routing**: Packets arrive on eth1 but replies leave via eth0
- **Dropped connections**: Remote hosts see replies from an unexpected source IP
- **Broken services**: Applications bound to secondary interfaces can't communicate properly

## The Solution

`sbr-config` creates per-interface routing tables, routes, and IP policy rules so that traffic originating from each interface's IP address is routed back through that same interface. It also configures the necessary kernel sysctl settings (reverse path filtering, ARP filtering).

## Requirements

- Linux (any distribution)
- Python 3.6+
- iproute2 (`ip` command)
- Root privileges

## Quick Start

```bash
# Clone
git clone https://github.com/WekaJosh/SBR-Config.git
cd SBR-Config

# Check current state (read-only)
sudo ./sbr-config --validate

# Configure interactively (shows changes, asks for confirmation)
sudo ./sbr-config --configure

# Configure and make persistent across reboots
sudo ./sbr-config --configure --persist
```

## Usage

```
Usage: sbr-config [OPTIONS]

Options:
  --validate              Check current SBR state and report findings
  --configure             Compute and apply needed SBR changes
  --rollback              Restore previous configuration from backup

  --force                 Skip interactive confirmation (use with --configure)
  --persist               Write persistent config that survives reboot
  --dry-run               Show proposed changes without applying them

  --exclude IFACE         Exclude interface from SBR (repeatable)
  --include IFACE         Only configure these interfaces (repeatable)

  --backup-file PATH      Specific backup file for --rollback
  --log-file PATH         Log file (default: /var/log/sbr-config.log)
  --no-color              Disable colored output
  -v, --verbose           Increase verbosity (-vv for debug)
  -q, --quiet             Suppress non-error output
  --version               Show version
```

## Modes

### Validate (`--validate`)

Read-only inspection of the current system. Reports what's correctly configured and what needs fixing:

```bash
sudo ./sbr-config --validate
```

Output shows each interface with pass/fail checks for routing tables, routes, rules, and sysctl settings.

### Configure (`--configure`)

Detects the current state, computes needed changes, and presents them with explanations before applying:

```bash
# Interactive (shows changes, asks before applying)
sudo ./sbr-config --configure

# Non-interactive (applies without asking)
sudo ./sbr-config --configure --force

# Preview only (shows what would change)
sudo ./sbr-config --configure --dry-run

# Also write boot-persistent configuration
sudo ./sbr-config --configure --persist
```

Each proposed change includes:
- **What**: The exact command to be executed
- **Why**: An explanation of why the change is necessary

### Rollback (`--rollback`)

Restores the system to its state before the last configuration:

```bash
# Restore from latest backup
sudo ./sbr-config --rollback

# Restore from a specific backup
sudo ./sbr-config --rollback --backup-file /var/lib/sbr-config/backups/state_20240115_143022.json
```

State backups are saved automatically before every configuration run.

## What It Configures

For each non-default network interface, `sbr-config` creates:

| Component | Example | Purpose |
|-----------|---------|---------|
| Routing table | `100 sbr_eth1` in `/etc/iproute2/rt_tables` | Dedicated table for eth1's routes |
| Subnet route | `ip route add 10.0.2.0/24 dev eth1 table sbr_eth1` | Reach the local network segment |
| Default route | `ip route add default via 10.0.2.1 dev eth1 table sbr_eth1` | Reach remote networks via eth1's gateway |
| Policy rule | `ip rule add from 10.0.2.50 table sbr_eth1` | Direct eth1's traffic to its table |

### Sysctl Settings

| Setting | Value | Purpose |
|---------|-------|---------|
| `net.ipv4.conf.all.rp_filter` | `2` | Loose reverse path filtering (required for SBR) |
| `net.ipv4.conf.<iface>.rp_filter` | `2` | Per-interface loose RP filter |
| `net.ipv4.conf.all.arp_filter` | `1` | Prevent ARP flux on multi-NIC systems |
| `net.ipv4.conf.all.arp_announce` | `2` | Use best local address for ARP |

## Persistence

With `--persist`, the tool writes configuration appropriate for the detected network manager:

| Network Manager | Persistence Method |
|----------------|--------------------|
| **NetworkManager** | Dispatcher script in `/etc/NetworkManager/dispatcher.d/` |
| **systemd-networkd** | `.network` files in `/etc/systemd/network/` |
| **ifupdown** | `post-up`/`pre-down` in `/etc/network/interfaces` |
| **Netplan** | YAML in `/etc/netplan/90-sbr-config.yaml` |

Sysctl settings are persisted to `/etc/sysctl.d/90-sbr-config.conf` regardless of network manager.

## Gateway Detection

For non-default interfaces, the tool tries multiple strategies to find the gateway:

1. Existing routes in custom routing tables
2. DHCP lease files (`/var/lib/dhclient/`, `/var/lib/dhcp/`, etc.)
3. NetworkManager (`nmcli`)
4. systemd-networkd config files
5. Common `.1` address heuristic

If no gateway can be detected, the interface is skipped with a warning.

## Backups

State backups are stored in `/var/lib/sbr-config/backups/` as JSON files containing:
- All interface configurations
- Routing table entries
- All routes and rules
- Sysctl values
- Raw file contents for exact restoration

A `latest.json` symlink always points to the most recent backup.

## Interface Filtering

```bash
# Only configure specific interfaces
sudo ./sbr-config --configure --include eth1 --include eth2

# Exclude interfaces from SBR
sudo ./sbr-config --configure --exclude docker0 --exclude virbr0
```

## Supported Distributions

Works on any Linux distribution with iproute2 and Python 3.6+, including:
- Ubuntu / Debian
- RHEL / CentOS / Rocky / Alma
- Fedora
- SUSE / openSUSE
- Arch Linux
- Amazon Linux

## License

MIT
