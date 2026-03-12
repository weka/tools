"""Abstract base class for persistence backends."""

from abc import ABC, abstractmethod
from typing import List

from ..models import InterfaceInfo, RoutingTable


class PersistenceBackend(ABC):
    """Base class that all persistence backends must implement."""

    @abstractmethod
    def write_config(
        self,
        interfaces: List[InterfaceInfo],
        tables: List[RoutingTable],
    ) -> List[str]:
        """Write persistent configuration files.

        Args:
            interfaces: Non-default interfaces with SBR configured.
            tables: Routing table assignments.

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
