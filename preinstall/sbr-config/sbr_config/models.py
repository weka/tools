"""Data models for sbr-config.

Plain classes (no dataclasses) for Python 3.6 compatibility.
"""

from enum import Enum
from typing import Dict, List, Optional


class NetworkManagerType(Enum):
    NETWORKMANAGER = "NetworkManager"
    SYSTEMD_NETWORKD = "systemd-networkd"
    IFUPDOWN = "ifupdown"
    NETPLAN_NETWORKD = "netplan+systemd-networkd"
    NETPLAN_NM = "netplan+NetworkManager"
    UNKNOWN = "unknown"


class ChangeType(Enum):
    ADD_RT_TABLE = "add_routing_table"
    ADD_ROUTE = "add_route"
    ADD_RULE = "add_rule"
    SET_SYSCTL = "set_sysctl"
    DEL_ROUTE = "delete_route"
    DEL_RULE = "delete_rule"


class InterfaceInfo(object):
    """Represents a discovered network interface."""

    def __init__(
        self,
        name,            # type: str
        ip_address,      # type: str
        prefix_length,   # type: int
        subnet,          # type: str
        gateway,         # type: Optional[str]
        mac_address,     # type: str
        is_up,           # type: bool
        is_loopback,     # type: bool
        is_default_route_interface,  # type: bool
        mtu,             # type: int
    ):
        self.name = name
        self.ip_address = ip_address
        self.prefix_length = prefix_length
        self.subnet = subnet
        self.gateway = gateway
        self.mac_address = mac_address
        self.is_up = is_up
        self.is_loopback = is_loopback
        self.is_default_route_interface = is_default_route_interface
        self.mtu = mtu

    @property
    def cidr(self):
        # type: () -> str
        return "{}/{}".format(self.ip_address, self.prefix_length)

    def _asdict(self):
        # type: () -> dict
        return {
            "name": self.name,
            "ip_address": self.ip_address,
            "prefix_length": self.prefix_length,
            "subnet": self.subnet,
            "gateway": self.gateway,
            "mac_address": self.mac_address,
            "is_up": self.is_up,
            "is_loopback": self.is_loopback,
            "is_default_route_interface": self.is_default_route_interface,
            "mtu": self.mtu,
        }


class RoutingTable(object):
    """Represents an entry in /etc/iproute2/rt_tables."""

    def __init__(self, number, name):
        # type: (int, str) -> None
        self.number = number
        self.name = name

    def _asdict(self):
        # type: () -> dict
        return {"number": self.number, "name": self.name}


class Route(object):
    """Represents a single ip route entry."""

    def __init__(
        self,
        destination,     # type: str
        gateway,         # type: Optional[str]
        device,          # type: str
        source=None,     # type: Optional[str]
        table=None,      # type: Optional[str]
        metric=None,     # type: Optional[int]
        scope=None,      # type: Optional[str]
        protocol=None,   # type: Optional[str]
    ):
        self.destination = destination
        self.gateway = gateway
        self.device = device
        self.source = source
        self.table = table
        self.metric = metric
        self.scope = scope
        self.protocol = protocol

    def to_args(self):
        # type: () -> str
        """Convert route to ip-route command arguments."""
        parts = [self.destination]
        if self.gateway:
            parts.extend(["via", self.gateway])
        parts.extend(["dev", self.device])
        if self.source:
            parts.extend(["src", self.source])
        if self.table:
            parts.extend(["table", self.table])
        if self.metric is not None:
            parts.extend(["metric", str(self.metric)])
        if self.scope:
            parts.extend(["scope", self.scope])
        return " ".join(parts)

    def _asdict(self):
        # type: () -> dict
        return {
            "destination": self.destination,
            "gateway": self.gateway,
            "device": self.device,
            "source": self.source,
            "table": self.table,
            "metric": self.metric,
            "scope": self.scope,
            "protocol": self.protocol,
        }


class Rule(object):
    """Represents a single ip rule entry."""

    def __init__(
        self,
        priority,         # type: int
        selector_from=None,  # type: Optional[str]
        selector_to=None,    # type: Optional[str]
        table=None,          # type: Optional[str]
        iif=None,            # type: Optional[str]
        fwmark=None,         # type: Optional[str]
    ):
        self.priority = priority
        self.selector_from = selector_from
        self.selector_to = selector_to
        self.table = table
        self.iif = iif
        self.fwmark = fwmark

    def to_args(self):
        # type: () -> str
        """Convert rule to ip-rule command arguments."""
        parts = []
        if self.selector_from:
            parts.extend(["from", self.selector_from])
        if self.selector_to:
            parts.extend(["to", self.selector_to])
        if self.table:
            parts.extend(["table", self.table])
        if self.iif:
            parts.extend(["iif", self.iif])
        if self.fwmark:
            parts.extend(["fwmark", self.fwmark])
        parts.extend(["priority", str(self.priority)])
        return " ".join(parts)

    def _asdict(self):
        # type: () -> dict
        return {
            "priority": self.priority,
            "selector_from": self.selector_from,
            "selector_to": self.selector_to,
            "table": self.table,
            "iif": self.iif,
            "fwmark": self.fwmark,
        }


class SysctlSetting(object):
    """Represents a sysctl key/value pair."""

    def __init__(
        self,
        key,              # type: str
        current_value,    # type: Optional[str]
        required_value,   # type: str
        description,      # type: str
        reason,           # type: str
    ):
        self.key = key
        self.current_value = current_value
        self.required_value = required_value
        self.description = description
        self.reason = reason

    @property
    def is_correct(self):
        # type: () -> bool
        return self.current_value == self.required_value


class SystemState(object):
    """Complete snapshot of current routing state for backup/comparison."""

    def __init__(
        self,
        interfaces,         # type: List[InterfaceInfo]
        routing_tables,     # type: List[RoutingTable]
        routes_main,        # type: List[Route]
        routes_by_table,    # type: Dict[str, List[Route]]
        rules,              # type: List[Rule]
        rt_tables_file_content,  # type: str
        sysctl_values,      # type: Dict[str, str]
        network_manager,    # type: NetworkManagerType
        timestamp,          # type: str
    ):
        self.interfaces = interfaces
        self.routing_tables = routing_tables
        self.routes_main = routes_main
        self.routes_by_table = routes_by_table
        self.rules = rules
        self.rt_tables_file_content = rt_tables_file_content
        self.sysctl_values = sysctl_values
        self.network_manager = network_manager
        self.timestamp = timestamp

    def to_dict(self):
        # type: () -> dict
        """Serialize to a JSON-compatible dict."""
        d = {}
        d["interfaces"] = [i._asdict() for i in self.interfaces]
        d["routing_tables"] = [t._asdict() for t in self.routing_tables]
        d["routes_main"] = [r._asdict() for r in self.routes_main]
        d["routes_by_table"] = {
            k: [r._asdict() for r in v]
            for k, v in self.routes_by_table.items()
        }
        d["rules"] = [r._asdict() for r in self.rules]
        d["rt_tables_file_content"] = self.rt_tables_file_content
        d["sysctl_values"] = self.sysctl_values
        d["network_manager"] = self.network_manager.value
        d["timestamp"] = self.timestamp
        return d


class PlannedChange(object):
    """A single atomic change to be applied."""

    def __init__(
        self,
        change_type,         # type: ChangeType
        description,         # type: str
        reason,              # type: str
        command,             # type: str
        interface=None,      # type: Optional[str]
        rollback_command=None,  # type: Optional[str]
    ):
        self.change_type = change_type
        self.description = description
        self.reason = reason
        self.command = command
        self.interface = interface
        self.rollback_command = rollback_command

    def to_dict(self):
        # type: () -> dict
        return {
            "change_type": self.change_type.value,
            "description": self.description,
            "reason": self.reason,
            "command": self.command,
            "interface": self.interface,
            "rollback_command": self.rollback_command,
        }


class ValidationResult(object):
    """Result of validating one aspect of SBR config."""

    def __init__(
        self,
        interface_name,    # type: str
        check_name,        # type: str
        is_correct,        # type: bool
        current_value,     # type: str
        expected_value,    # type: str
        fix_description,   # type: str
    ):
        self.interface_name = interface_name
        self.check_name = check_name
        self.is_correct = is_correct
        self.current_value = current_value
        self.expected_value = expected_value
        self.fix_description = fix_description

    @property
    def status_symbol(self):
        # type: () -> str
        return "PASS" if self.is_correct else "FAIL"
