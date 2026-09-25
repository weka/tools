"""Abstract base class for persistence backends."""

from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from ..constants import (
    RULE_PRIORITY_INCREMENT,
    RULE_PRIORITY_START,
    TABLE_NUMBER_START,
)
from ..models import InterfaceInfo, PlannedChange, RoutingTable


def rule_priority_for(
    ip_address: str,
    table_number: int,
    rule_priorities: Optional[Dict[str, int]],
) -> int:
    """Priority to persist for one source IP's rule.

    Prefers the priority actually in effect (from kernel rules or this
    run's plan, collected by persistence.py) so persisted files always
    match runtime -- including custom --rule-priority bases. Falls back
    to the default derived formula, clamped so pre-existing sbr_ tables
    numbered below the allocation base can't produce an invalid value.
    """
    if rule_priorities and ip_address in rule_priorities:
        return rule_priorities[ip_address]
    return max(
        RULE_PRIORITY_START,
        RULE_PRIORITY_START
        + (table_number - TABLE_NUMBER_START) * RULE_PRIORITY_INCREMENT,
    )


def group_by_name(interfaces: List[InterfaceInfo]) -> List[Tuple[str, List[InterfaceInfo]]]:
    """Group interface entries by name, preserving order.

    state.interfaces holds one entry per IPv4 address, so an interface
    with several addresses appears several times. Backends must emit ONE
    config per interface covering all of its addresses -- duplicate
    stanzas/files/YAML keys are either invalid or silently drop rules.
    """
    grouped = OrderedDict()
    for iface in interfaces:
        grouped.setdefault(iface.name, []).append(iface)
    return list(grouped.items())


class PersistenceBackend(ABC):
    """Base class that all persistence backends must implement."""

    @abstractmethod
    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
        changes: List[PlannedChange],
        rule_priorities: Optional[Dict[str, int]] = None,
    ) -> List[str]:
        """Write persistent configuration files.

        Args:
            interfaces: Non-default interfaces with SBR configured.
            tables: Routing table assignments.
            changes: The planned changes that were applied.
            rule_priorities: Source IP -> rule priority actually in
                             effect (see persistence._collect_rule_priorities).

        Returns:
            List of file paths that were created or modified.
        """
        ...

    @abstractmethod
    def remove_config(self) -> List[str]:
        """Remove previously written persistent configuration.

        Returns:
            List of file paths that were removed or restored.
        """
        ...

    @abstractmethod
    def describe(self) -> str:
        """Human-readable description of what this backend writes and where.

        Returns:
            Description string.
        """
        ...
