"""Abstract base class for persistence backends."""

from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import List, Tuple

from ..models import InterfaceInfo, PlannedChange, RoutingTable


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
    ) -> List[str]:
        """Write persistent configuration files.

        Args:
            interfaces: Non-default interfaces with SBR configured.
            tables: Routing table assignments.
            changes: The planned changes that were applied.

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
