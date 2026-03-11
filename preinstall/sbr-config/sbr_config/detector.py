"""Discover interfaces, IPs, gateways, routes, rules, and network manager type."""

import glob
import ipaddress
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .constants import (
    DHCP_LEASE_PATHS,
    INTERFACES_FILE,
    NETPLAN_DIR,
    RT_TABLES_PATH,
    SYSTEMD_NETWORK_DIR,
)
from .exceptions import DetectionError
from .models import (
    InterfaceInfo,
    NetworkManagerType,
    Route,
    RoutingTable,
    Rule,
    SystemState,
)
from .sysctl import read_all_sysctl_values
from .utils import command_exists, ip_json_supported, read_file, run_command

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_system_state(
    exclude: Optional[List[str]] = None,
    include: Optional[List[str]] = None,
) -> SystemState:
    """Detect the complete system routing state.

    Args:
        exclude: Interface names to skip.
        include: If set, only include these interface names.

    Returns:
        SystemState with all detected information.
    """
    use_json = ip_json_supported()
    logger.info("ip JSON mode: %s", "supported" if use_json else "fallback to text")

    # Detect interfaces
    interfaces = _detect_interfaces(use_json)

    # Filter interfaces
    if include:
        interfaces = [i for i in interfaces if i.name in include or i.is_loopback]
    if exclude:
        interfaces = [i for i in interfaces if i.name not in exclude]

    # Detect default route and mark the default interface
    default_gw, default_dev = _detect_default_route(use_json)
    for iface in interfaces:
        iface.is_default_route_interface = (iface.name == default_dev)
        if iface.name == default_dev and iface.gateway is None:
            iface.gateway = default_gw

    # Detect gateways for non-default interfaces
    for iface in interfaces:
        if iface.is_loopback or iface.is_default_route_interface:
            continue
        if iface.gateway is None:
            iface.gateway = _detect_gateway(iface, use_json)

    # Detect routing tables
    rt_tables_content = read_file(RT_TABLES_PATH) or ""
    routing_tables = _parse_rt_tables(rt_tables_content)

    # Detect routes and rules
    routes_main = _detect_routes(use_json, table="main")
    routes_by_table = {}
    for rt in routing_tables:
        table_routes = _detect_routes(use_json, table=rt.name)
        if table_routes:
            routes_by_table[rt.name] = table_routes
    rules = _detect_rules(use_json)

    # Detect sysctl values
    iface_names = [i.name for i in interfaces if not i.is_loopback]
    sysctl_values = read_all_sysctl_values(iface_names)

    # Detect network manager
    network_manager = _detect_network_manager()

    return SystemState(
        interfaces=interfaces,
        routing_tables=routing_tables,
        routes_main=routes_main,
        routes_by_table=routes_by_table,
        rules=rules,
        rt_tables_file_content=rt_tables_content,
        sysctl_values=sysctl_values,
        network_manager=network_manager,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Interface detection
# ---------------------------------------------------------------------------

def _detect_interfaces(use_json: bool) -> List[InterfaceInfo]:
    """Detect all network interfaces with their IP addresses."""
    if use_json:
        return _detect_interfaces_json()
    return _detect_interfaces_text()


def _detect_interfaces_json() -> List[InterfaceInfo]:
    """Detect interfaces using `ip -j addr show`."""
    result = run_command("ip -j addr show", check=True)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise DetectionError(f"Failed to parse 'ip -j addr show' output: {e}")

    interfaces = []
    for entry in data:
        name = entry.get("ifname", "")
        flags = entry.get("flags", [])
        is_loopback = "LOOPBACK" in flags
        is_up = entry.get("operstate", "").upper() in ("UP", "UNKNOWN")
        mac = entry.get("address", "")
        mtu = entry.get("mtu", 1500)

        # Find IPv4 addresses
        for addr_info in entry.get("addr_info", []):
            if addr_info.get("family") != "inet":
                continue
            ip_addr = addr_info.get("local", "")
            prefix = addr_info.get("prefixlen", 24)
            if not ip_addr:
                continue

            # Compute subnet
            try:
                network = ipaddress.IPv4Network(f"{ip_addr}/{prefix}", strict=False)
                subnet = str(network)
            except ValueError:
                subnet = f"{ip_addr}/{prefix}"

            interfaces.append(InterfaceInfo(
                name=name,
                ip_address=ip_addr,
                prefix_length=prefix,
                subnet=subnet,
                gateway=None,  # Filled later
                mac_address=mac,
                is_up=is_up,
                is_loopback=is_loopback,
                is_default_route_interface=False,  # Filled later
                mtu=mtu,
            ))

    logger.info("Detected %d interfaces (JSON mode)", len(interfaces))
    return interfaces


def _detect_interfaces_text() -> List[InterfaceInfo]:
    """Detect interfaces by parsing `ip addr show` text output."""
    result = run_command("ip addr show", check=True)
    interfaces = []

    current_name = ""
    current_mac = ""
    current_mtu = 1500
    current_flags = ""
    current_state = ""

    for line in result.stdout.splitlines():
        # Interface header: "2: eth0: <BROADCAST,...> mtu 1500 ... state UP"
        m = re.match(r'^\d+:\s+(\S+?):\s+<([^>]*)>.*mtu\s+(\d+)', line)
        if m:
            current_name = m.group(1).rstrip(":")
            current_flags = m.group(2)
            current_mtu = int(m.group(3))
            # Extract state
            state_m = re.search(r'state\s+(\S+)', line)
            current_state = state_m.group(1) if state_m else "UNKNOWN"
            continue

        # MAC address: "    link/ether aa:bb:cc:dd:ee:ff"
        m = re.match(r'^\s+link/ether\s+([\da-f:]+)', line)
        if m:
            current_mac = m.group(1)
            continue

        # IPv4 address: "    inet 10.0.1.50/24 ..."
        m = re.match(r'^\s+inet\s+([\d.]+)/(\d+)', line)
        if m:
            ip_addr = m.group(1)
            prefix = int(m.group(2))
            is_loopback = "LOOPBACK" in current_flags
            is_up = current_state.upper() in ("UP", "UNKNOWN")

            try:
                network = ipaddress.IPv4Network(f"{ip_addr}/{prefix}", strict=False)
                subnet = str(network)
            except ValueError:
                subnet = f"{ip_addr}/{prefix}"

            interfaces.append(InterfaceInfo(
                name=current_name,
                ip_address=ip_addr,
                prefix_length=prefix,
                subnet=subnet,
                gateway=None,
                mac_address=current_mac,
                is_up=is_up,
                is_loopback=is_loopback,
                is_default_route_interface=False,
                mtu=current_mtu,
            ))

    logger.info("Detected %d interfaces (text mode)", len(interfaces))
    return interfaces


# ---------------------------------------------------------------------------
# Route detection
# ---------------------------------------------------------------------------

def _detect_default_route(use_json: bool) -> Tuple[Optional[str], Optional[str]]:
    """Detect the default route gateway and device.

    Returns:
        (gateway_ip, device_name) or (None, None) if no default route.
    """
    if use_json:
        result = run_command("ip -j route show default", check=False)
        if result.returncode == 0 and result.stdout.strip():
            try:
                routes = json.loads(result.stdout)
                for r in routes:
                    if r.get("dst") == "default":
                        return r.get("gateway"), r.get("dev")
            except json.JSONDecodeError:
                pass

    # Fallback: text parsing
    result = run_command("ip route show default", check=False)
    for line in result.stdout.splitlines():
        m = re.match(r'^default\s+via\s+(\S+)\s+dev\s+(\S+)', line)
        if m:
            return m.group(1), m.group(2)

    logger.warning("No default route found")
    return None, None


def _detect_routes(use_json: bool, table: str = "main") -> List[Route]:
    """Detect routes in a specific routing table."""
    if use_json:
        result = run_command(f"ip -j route show table {table}", check=False)
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                return [_parse_route_json(r, table) for r in data]
            except json.JSONDecodeError:
                pass

    # Fallback: text parsing
    result = run_command(f"ip route show table {table}", check=False)
    routes = []
    for line in result.stdout.splitlines():
        route = _parse_route_text(line, table)
        if route:
            routes.append(route)
    return routes


def _parse_route_json(data: dict, table: str) -> Route:
    """Parse a single route from JSON output."""
    return Route(
        destination=data.get("dst", ""),
        gateway=data.get("gateway"),
        device=data.get("dev", ""),
        source=data.get("prefsrc"),
        table=table,
        metric=data.get("metric"),
        scope=data.get("scope"),
        protocol=data.get("protocol"),
    )


def _parse_route_text(line: str, table: str) -> Optional[Route]:
    """Parse a single route from text output."""
    line = line.strip()
    if not line:
        return None

    parts = line.split()
    if not parts:
        return None

    destination = parts[0]
    gateway = None
    device = ""
    source = None
    metric = None
    scope = None
    protocol = None

    i = 1
    while i < len(parts):
        if parts[i] == "via" and i + 1 < len(parts):
            gateway = parts[i + 1]
            i += 2
        elif parts[i] == "dev" and i + 1 < len(parts):
            device = parts[i + 1]
            i += 2
        elif parts[i] == "src" and i + 1 < len(parts):
            source = parts[i + 1]
            i += 2
        elif parts[i] == "metric" and i + 1 < len(parts):
            try:
                metric = int(parts[i + 1])
            except ValueError:
                pass
            i += 2
        elif parts[i] == "scope" and i + 1 < len(parts):
            scope = parts[i + 1]
            i += 2
        elif parts[i] == "proto" and i + 1 < len(parts):
            protocol = parts[i + 1]
            i += 2
        else:
            i += 1

    return Route(
        destination=destination,
        gateway=gateway,
        device=device,
        source=source,
        table=table,
        metric=metric,
        scope=scope,
        protocol=protocol,
    )


# ---------------------------------------------------------------------------
# Rule detection
# ---------------------------------------------------------------------------

def _detect_rules(use_json: bool) -> List[Rule]:
    """Detect all IP policy rules."""
    if use_json:
        result = run_command("ip -j rule show", check=False)
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                return [_parse_rule_json(r) for r in data]
            except json.JSONDecodeError:
                pass

    # Fallback: text parsing
    result = run_command("ip rule show", check=False)
    rules = []
    for line in result.stdout.splitlines():
        rule = _parse_rule_text(line)
        if rule:
            rules.append(rule)
    return rules


def _parse_rule_json(data: dict) -> Rule:
    """Parse a single rule from JSON output."""
    return Rule(
        priority=data.get("priority", 0),
        selector_from=data.get("src"),
        selector_to=data.get("dst"),
        table=data.get("table"),
        iif=data.get("iif"),
        fwmark=data.get("fwmark"),
    )


def _parse_rule_text(line: str) -> Optional[Rule]:
    """Parse a single rule from text output.

    Format: "100:  from 10.0.2.50 lookup sbr_eth1"
    """
    line = line.strip()
    if not line:
        return None

    # Extract priority
    m = re.match(r'^(\d+):\s*(.*)', line)
    if not m:
        return None

    priority = int(m.group(1))
    rest = m.group(2)

    selector_from = None
    selector_to = None
    table = None
    iif = None
    fwmark = None

    parts = rest.split()
    i = 0
    while i < len(parts):
        if parts[i] == "from" and i + 1 < len(parts):
            val = parts[i + 1]
            if val != "all":
                selector_from = val
            i += 2
        elif parts[i] == "to" and i + 1 < len(parts):
            val = parts[i + 1]
            if val != "all":
                selector_to = val
            i += 2
        elif parts[i] in ("lookup", "table") and i + 1 < len(parts):
            table = parts[i + 1]
            i += 2
        elif parts[i] == "iif" and i + 1 < len(parts):
            iif = parts[i + 1]
            i += 2
        elif parts[i] == "fwmark" and i + 1 < len(parts):
            fwmark = parts[i + 1]
            i += 2
        else:
            i += 1

    return Rule(
        priority=priority,
        selector_from=selector_from,
        selector_to=selector_to,
        table=table,
        iif=iif,
        fwmark=fwmark,
    )


# ---------------------------------------------------------------------------
# Routing table file parsing
# ---------------------------------------------------------------------------

def _parse_rt_tables(content: str) -> List[RoutingTable]:
    """Parse /etc/iproute2/rt_tables content.

    Returns:
        List of RoutingTable entries (excluding reserved tables).
    """
    tables = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            number = int(parts[0])
        except ValueError:
            continue
        name = parts[1].strip()
        tables.append(RoutingTable(number=number, name=name))
    return tables


# ---------------------------------------------------------------------------
# Gateway detection for non-default interfaces
# ---------------------------------------------------------------------------

def _detect_gateway(iface: InterfaceInfo, use_json: bool) -> Optional[str]:
    """Try multiple strategies to detect the gateway for an interface.

    Strategies in priority order:
    1. Existing routes in custom SBR tables
    2. DHCP lease files
    3. NetworkManager (nmcli)
    4. Common .1 heuristic
    """
    gw = _gateway_from_existing_routes(iface, use_json)
    if gw:
        logger.info("Gateway for %s from existing routes: %s", iface.name, gw)
        return gw

    gw = _gateway_from_dhcp_leases(iface)
    if gw:
        logger.info("Gateway for %s from DHCP lease: %s", iface.name, gw)
        return gw

    gw = _gateway_from_nmcli(iface)
    if gw:
        logger.info("Gateway for %s from nmcli: %s", iface.name, gw)
        return gw

    gw = _gateway_from_networkd(iface)
    if gw:
        logger.info("Gateway for %s from systemd-networkd: %s", iface.name, gw)
        return gw

    # No heuristic guessing -- if we can't find a gateway from a
    # reliable source, leave it as None.  Non-routable interfaces
    # (storage, cluster interconnects, etc.) legitimately have no
    # gateway and SBR should still handle them (table + subnet route
    # + rule, but no default route).
    logger.info(
        "No gateway found for %s -- will configure SBR without a "
        "default route in its table (subnet-only routing)",
        iface.name,
    )
    return None


def _gateway_from_existing_routes(iface: InterfaceInfo, use_json: bool) -> Optional[str]:
    """Check if there's already a default route via this interface in any table."""
    result = run_command("ip route show table all default", check=False)
    for line in result.stdout.splitlines():
        if f"dev {iface.name}" in line:
            m = re.search(r'via\s+(\S+)', line)
            if m:
                return m.group(1)
    return None


def _gateway_from_dhcp_leases(iface: InterfaceInfo) -> Optional[str]:
    """Search DHCP lease files for gateway information."""
    for pattern in DHCP_LEASE_PATHS:
        path = pattern.format(iface=iface.name)
        matched_files = glob.glob(path)
        for lease_file in matched_files:
            try:
                content = read_file(lease_file)
                if not content:
                    continue
                # dhclient format: "option routers 10.0.2.1;"
                m = re.search(r'option\s+routers\s+([\d.]+)', content)
                if m:
                    return m.group(1)
                # systemd-networkd lease format: "ROUTER=10.0.2.1"
                m = re.search(r'ROUTER=([\d.]+)', content)
                if m:
                    return m.group(1)
            except Exception as e:
                logger.debug("Error reading lease file %s: %s", lease_file, e)
    return None


def _gateway_from_nmcli(iface: InterfaceInfo) -> Optional[str]:
    """Try to get gateway from NetworkManager via nmcli."""
    if not command_exists("nmcli"):
        return None
    result = run_command(
        f"nmcli -t -f IP4.GATEWAY device show {iface.name}",
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("IP4.GATEWAY:"):
            gw = line.split(":", 1)[1].strip()
            if gw and gw != "--":
                return gw
    return None


def _gateway_from_networkd(iface: InterfaceInfo) -> Optional[str]:
    """Try to get gateway from systemd-networkd config files."""
    if not os.path.isdir(SYSTEMD_NETWORK_DIR):
        return None
    for fname in sorted(os.listdir(SYSTEMD_NETWORK_DIR)):
        if not fname.endswith(".network"):
            continue
        content = read_file(os.path.join(SYSTEMD_NETWORK_DIR, fname))
        if not content:
            continue
        # Check if this file matches our interface
        if re.search(rf'\[Match\]\s*\n\s*Name\s*=\s*{re.escape(iface.name)}\b', content):
            m = re.search(r'Gateway\s*=\s*([\d.]+)', content)
            if m:
                return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Network manager detection
# ---------------------------------------------------------------------------

def _detect_network_manager() -> NetworkManagerType:
    """Detect which network management system is active."""
    # Check netplan first (it's a frontend)
    if os.path.isdir(NETPLAN_DIR) and command_exists("netplan"):
        yaml_files = glob.glob(os.path.join(NETPLAN_DIR, "*.yaml"))
        if yaml_files:
            renderer = _detect_netplan_renderer(yaml_files)
            if renderer == "NetworkManager":
                logger.info("Detected: netplan with NetworkManager renderer")
                return NetworkManagerType.NETPLAN_NM
            logger.info("Detected: netplan with systemd-networkd renderer")
            return NetworkManagerType.NETPLAN_NETWORKD

    # Check NetworkManager
    if _service_is_active("NetworkManager.service") or _service_is_active("NetworkManager"):
        logger.info("Detected: NetworkManager")
        return NetworkManagerType.NETWORKMANAGER

    # Check systemd-networkd
    if _service_is_active("systemd-networkd.service") or _service_is_active("systemd-networkd"):
        logger.info("Detected: systemd-networkd")
        return NetworkManagerType.SYSTEMD_NETWORKD

    # Check ifupdown
    if os.path.exists(INTERFACES_FILE) and (command_exists("ifup") or command_exists("ifdown")):
        logger.info("Detected: ifupdown")
        return NetworkManagerType.IFUPDOWN

    logger.warning("Could not detect network manager")
    return NetworkManagerType.UNKNOWN


def _detect_netplan_renderer(yaml_files: List[str]) -> str:
    """Detect netplan's renderer from its YAML config files."""
    for path in yaml_files:
        content = read_file(path)
        if not content:
            continue
        m = re.search(r'renderer:\s*(\S+)', content)
        if m:
            return m.group(1)
    # Default renderer is systemd-networkd
    return "networkd"


def _service_is_active(service: str) -> bool:
    """Check if a systemd service is active."""
    result = run_command(f"systemctl is-active {service}", check=False)
    return result.stdout.strip() == "active"
