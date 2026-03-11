"""Compute ordered change sets with human-readable explanations."""

import logging
from typing import Dict, List, Set

from .constants import (
    RESERVED_TABLE_NAMES,
    RESERVED_TABLE_NUMBERS,
    RULE_PRIORITY_INCREMENT,
    RULE_PRIORITY_START,
    TABLE_NAME_PREFIX,
    TABLE_NUMBER_MAX,
    TABLE_NUMBER_START,
)
from .models import (
    ChangeType,
    InterfaceInfo,
    PlannedChange,
    SystemState,
    ValidationResult,
)
from .sysctl import plan_sysctl_changes

logger = logging.getLogger(__name__)


def plan_changes(
    state: SystemState,
    validation_results: List[ValidationResult],
) -> List[PlannedChange]:
    """Generate an ordered list of changes needed to establish correct SBR.

    Changes are ordered for correct application:
    1. Sysctl settings
    2. Routing table entries in /etc/iproute2/rt_tables
    3. Subnet routes in custom tables
    4. Default routes in custom tables
    5. IP policy rules

    Args:
        state: Current system state.
        validation_results: Results from validator.

    Returns:
        Ordered list of PlannedChange entries.
    """
    changes: List[PlannedChange] = []

    # Collect failed checks by interface
    failed_by_iface: Dict[str, Set[str]] = {}
    for r in validation_results:
        if not r.is_correct:
            failed_by_iface.setdefault(r.interface_name, set()).add(r.check_name)

    # No failures? Nothing to do.
    if not failed_by_iface:
        return []

    # Plan sysctl changes first
    non_default_ifaces = [
        i.name for i in state.interfaces
        if not i.is_loopback and not i.is_default_route_interface and i.is_up
    ]
    sysctl_changes = plan_sysctl_changes(state.sysctl_values, non_default_ifaces)
    changes.extend(sysctl_changes)

    # Allocate table numbers for interfaces that need them
    used_numbers = {rt.number for rt in state.routing_tables}
    used_names = {rt.name for rt in state.routing_tables}
    table_assignments: Dict[str, int] = {}  # iface_name -> table_number

    # Pre-populate from existing tables
    for rt in state.routing_tables:
        if rt.name.startswith(TABLE_NAME_PREFIX):
            iface_name = rt.name[len(TABLE_NAME_PREFIX):]
            table_assignments[iface_name] = rt.number

    next_number = TABLE_NUMBER_START

    for iface in state.interfaces:
        if iface.is_loopback or iface.is_default_route_interface or not iface.is_up:
            continue

        iface_fails = failed_by_iface.get(iface.name, set())
        if not iface_fails:
            continue

        table_name = f"{TABLE_NAME_PREFIX}{iface.name}"

        # Phase 1: Routing table entry
        if "routing_table_exists" in iface_fails:
            # Allocate a table number
            if iface.name not in table_assignments:
                while (next_number in used_numbers
                       or next_number in RESERVED_TABLE_NUMBERS):
                    next_number += 1
                    if next_number > TABLE_NUMBER_MAX:
                        logger.error("Exhausted routing table numbers")
                        break
                table_assignments[iface.name] = next_number
                used_numbers.add(next_number)
                next_number += 1

            table_num = table_assignments.get(iface.name, next_number)
            changes.append(PlannedChange(
                change_type=ChangeType.ADD_RT_TABLE,
                description=f"Add routing table {table_num} '{table_name}'",
                reason=(
                    f"Interface {iface.name} has IP {iface.ip_address} but no dedicated "
                    f"routing table. Without its own table, response traffic from "
                    f"{iface.ip_address} will follow the main routing table's default "
                    f"route and exit via the wrong interface, causing asymmetric routing "
                    f"and dropped connections (the remote host sees replies from a "
                    f"different IP than it sent to)."
                ),
                command=f"echo '{table_num} {table_name}' >> /etc/iproute2/rt_tables",
                interface=iface.name,
                rollback_command=None,  # Handled by rt_tables file restore
            ))

        # Phase 2: Subnet route
        if "subnet_route_in_table" in iface_fails:
            route_cmd = (
                f"ip route add {iface.subnet} dev {iface.name} "
                f"src {iface.ip_address} table {table_name}"
            )
            del_cmd = (
                f"ip route del {iface.subnet} dev {iface.name} "
                f"table {table_name}"
            )
            changes.append(PlannedChange(
                change_type=ChangeType.ADD_ROUTE,
                description=(
                    f"Add subnet route {iface.subnet} dev {iface.name} "
                    f"table {table_name}"
                ),
                reason=(
                    f"Table '{table_name}' needs a route to the local subnet "
                    f"{iface.subnet} via {iface.name}. This allows the custom "
                    f"routing table to reach "
                    + (f"the gateway ({iface.gateway}) and " if iface.gateway else "")
                    + "other hosts on the local network segment."
                ),
                command=route_cmd,
                interface=iface.name,
                rollback_command=del_cmd,
            ))

        # Phase 3: Default route in custom table (only if gateway exists)
        if iface.gateway is not None and "default_route_in_table" in iface_fails:
            route_cmd = (
                f"ip route add default via {iface.gateway} "
                f"dev {iface.name} table {table_name}"
            )
            del_cmd = (
                f"ip route del default via {iface.gateway} "
                f"dev {iface.name} table {table_name}"
            )
            changes.append(PlannedChange(
                change_type=ChangeType.ADD_ROUTE,
                description=(
                    f"Add default route via {iface.gateway} dev {iface.name} "
                    f"table {table_name}"
                ),
                reason=(
                    f"Table '{table_name}' needs a default route so that traffic "
                    f"originating from {iface.ip_address} destined for remote "
                    f"networks can exit through {iface.name}'s gateway "
                    f"({iface.gateway}). Without this, only local-subnet traffic "
                    f"would work."
                ),
                command=route_cmd,
                interface=iface.name,
                rollback_command=del_cmd,
            ))

        # Phase 4: IP rule
        if "ip_rule_exists" in iface_fails:
            # Determine priority: find unused priority slot
            used_priorities = {r.priority for r in state.rules}
            priority = RULE_PRIORITY_START
            while priority in used_priorities:
                priority += RULE_PRIORITY_INCREMENT
            used_priorities.add(priority)

            rule_cmd = (
                f"ip rule add from {iface.ip_address} "
                f"table {table_name} priority {priority}"
            )
            del_cmd = (
                f"ip rule del from {iface.ip_address} "
                f"table {table_name} priority {priority}"
            )
            changes.append(PlannedChange(
                change_type=ChangeType.ADD_RULE,
                description=(
                    f"Add rule: from {iface.ip_address} lookup {table_name} "
                    f"(priority {priority})"
                ),
                reason=(
                    f"This IP policy rule tells the kernel that all traffic "
                    f"originating from {iface.ip_address} should consult table "
                    f"'{table_name}' instead of the main routing table. This is "
                    f"the key rule that ensures responses leave through the same "
                    f"interface they arrived on."
                ),
                command=rule_cmd,
                interface=iface.name,
                rollback_command=del_cmd,
            ))

    logger.info("Planned %d changes", len(changes))
    return changes
