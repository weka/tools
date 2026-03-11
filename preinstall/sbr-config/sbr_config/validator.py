"""Validation logic: check current state against correct SBR requirements."""

import logging
from typing import List, Optional

from .constants import TABLE_NAME_PREFIX
from .models import InterfaceInfo, Route, Rule, SystemState, ValidationResult
from .sysctl import validate_sysctl

logger = logging.getLogger(__name__)


def validate(state: SystemState) -> List[ValidationResult]:
    """Validate the current system state for correct source-based routing.

    Checks each non-default, non-loopback interface for:
    - Routing table entry exists
    - Subnet route in custom table
    - Default route in custom table
    - IP rule from interface IP to custom table
    - No conflicting rules

    Also validates sysctl settings.

    Args:
        state: The current system state from detector.

    Returns:
        List of ValidationResult entries (one per check).
    """
    results = []

    # Find the default route interface
    default_iface = _find_default_interface(state)

    # Validate each non-default interface
    for iface in state.interfaces:
        if iface.is_loopback:
            continue
        if iface.is_default_route_interface:
            results.append(ValidationResult(
                interface_name=iface.name,
                check_name="default_route_interface",
                is_correct=True,
                current_value=f"Default route via {iface.gateway or 'unknown'}",
                expected_value="Not modified by SBR",
                fix_description="",
            ))
            continue

        if not iface.is_up:
            results.append(ValidationResult(
                interface_name=iface.name,
                check_name="interface_state",
                is_correct=True,
                current_value="DOWN (skipped)",
                expected_value="Interface is down, skipping SBR checks",
                fix_description="",
            ))
            continue

        # Run SBR checks for this interface (with or without gateway)
        table_name = f"{TABLE_NAME_PREFIX}{iface.name}"
        results.extend(_validate_interface_sbr(iface, table_name, state))

    # Validate that the default route in main table is intact
    results.extend(_validate_default_route(state, default_iface))

    # Validate sysctl settings
    non_default_ifaces = [
        i.name for i in state.interfaces
        if not i.is_loopback and not i.is_default_route_interface and i.is_up
    ]
    results.extend(validate_sysctl(state.sysctl_values, non_default_ifaces))

    return results


def _find_default_interface(state: SystemState) -> Optional[InterfaceInfo]:
    """Find the interface carrying the default route."""
    for iface in state.interfaces:
        if iface.is_default_route_interface:
            return iface
    return None


def _validate_interface_sbr(
    iface: InterfaceInfo,
    table_name: str,
    state: SystemState,
) -> List[ValidationResult]:
    """Validate SBR configuration for a single interface."""
    results = []

    # Check 1: Routing table entry exists
    table_exists = any(
        rt.name == table_name for rt in state.routing_tables
    )
    results.append(ValidationResult(
        interface_name=iface.name,
        check_name="routing_table_exists",
        is_correct=table_exists,
        current_value=f"Table '{table_name}' {'exists' if table_exists else 'missing'}",
        expected_value=f"Table '{table_name}' in /etc/iproute2/rt_tables",
        fix_description=(
            f"Interface {iface.name} ({iface.ip_address}) needs a dedicated routing "
            f"table named '{table_name}' so traffic from this interface can be routed "
            f"independently of the main routing table."
        ) if not table_exists else "",
    ))

    # Check 2: Subnet route in custom table
    table_routes = state.routes_by_table.get(table_name, [])
    has_subnet_route = any(
        r.destination == iface.subnet and r.device == iface.name
        for r in table_routes
    )
    results.append(ValidationResult(
        interface_name=iface.name,
        check_name="subnet_route_in_table",
        is_correct=has_subnet_route,
        current_value=(
            f"Subnet route for {iface.subnet} "
            f"{'found' if has_subnet_route else 'missing'} in table {table_name}"
        ),
        expected_value=f"{iface.subnet} dev {iface.name} src {iface.ip_address} table {table_name}",
        fix_description=(
            f"Table '{table_name}' needs a route to the local subnet {iface.subnet} "
            f"via {iface.name} so the interface can reach its gateway."
        ) if not has_subnet_route else "",
    ))

    # Check 3: Default route in custom table (only if gateway is known)
    if iface.gateway is not None:
        has_default_route = any(
            r.destination == "default" and r.gateway == iface.gateway and r.device == iface.name
            for r in table_routes
        )
        results.append(ValidationResult(
            interface_name=iface.name,
            check_name="default_route_in_table",
            is_correct=has_default_route,
            current_value=(
                f"Default route via {iface.gateway} dev {iface.name} "
                f"{'found' if has_default_route else 'missing'} in table {table_name}"
            ),
            expected_value=f"default via {iface.gateway} dev {iface.name} table {table_name}",
            fix_description=(
                f"Table '{table_name}' needs a default route via {iface.gateway} "
                f"so traffic originating from {iface.ip_address} destined for remote "
                f"networks exits through {iface.name}'s gateway."
            ) if not has_default_route else "",
        ))
    else:
        # No gateway -- no default route needed (non-routable / subnet-only)
        results.append(ValidationResult(
            interface_name=iface.name,
            check_name="default_route_in_table",
            is_correct=True,
            current_value="No gateway -- default route not applicable",
            expected_value="No default route (non-routable interface)",
            fix_description="",
        ))

    # Check 4: IP rule exists
    has_rule = any(
        r.selector_from in (iface.ip_address, f"{iface.ip_address}/32")
        and r.table == table_name
        for r in state.rules
    )
    results.append(ValidationResult(
        interface_name=iface.name,
        check_name="ip_rule_exists",
        is_correct=has_rule,
        current_value=(
            f"Rule from {iface.ip_address} lookup {table_name} "
            f"{'found' if has_rule else 'missing'}"
        ),
        expected_value=f"from {iface.ip_address} lookup {table_name}",
        fix_description=(
            f"An IP rule is needed to direct traffic originating from "
            f"{iface.ip_address} to use table '{table_name}'. Without this rule, "
            f"the kernel uses the main routing table and responses may exit "
            f"via the wrong interface."
        ) if not has_rule else "",
    ))

    # Check 5: No conflicting rules
    conflicting = [
        r for r in state.rules
        if r.selector_from in (iface.ip_address, f"{iface.ip_address}/32")
        and r.table is not None
        and r.table != table_name
        and r.table not in ("main", "local", "default")
    ]
    has_conflict = len(conflicting) > 0
    if has_conflict:
        conflict_details = ", ".join(
            f"from {r.selector_from} lookup {r.table} (priority {r.priority})"
            for r in conflicting
        )
        results.append(ValidationResult(
            interface_name=iface.name,
            check_name="no_conflicting_rules",
            is_correct=False,
            current_value=f"Conflicting rules: {conflict_details}",
            expected_value="No rules from this IP pointing to other tables",
            fix_description=(
                f"Existing rules direct traffic from {iface.ip_address} to "
                f"table(s) other than '{table_name}'. This may conflict with "
                f"SBR configuration. Review and remove conflicting rules or "
                f"use --exclude {iface.name} to skip this interface."
            ),
        ))
    else:
        results.append(ValidationResult(
            interface_name=iface.name,
            check_name="no_conflicting_rules",
            is_correct=True,
            current_value="No conflicting rules found",
            expected_value="No conflicting rules",
            fix_description="",
        ))

    return results


def _validate_default_route(
    state: SystemState,
    default_iface: Optional[InterfaceInfo],
) -> List[ValidationResult]:
    """Validate that the main table's default route is intact."""
    results = []

    has_default = any(
        r.destination == "default" for r in state.routes_main
    )
    results.append(ValidationResult(
        interface_name="(main table)",
        check_name="default_route_intact",
        is_correct=has_default,
        current_value=(
            f"Default route {'present' if has_default else 'MISSING'} in main table"
        ),
        expected_value="Default route present in main table",
        fix_description=(
            "The main routing table has no default route. This means the system "
            "has no general internet connectivity path. SBR configuration should "
            "not remove the main table's default route."
        ) if not has_default else "",
    ))

    return results
