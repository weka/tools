"""Custom exception hierarchy for sbr-config."""


class SbrConfigError(Exception):
    """Base exception for all sbr-config errors."""
    pass


class DetectionError(SbrConfigError):
    """Failed to detect interfaces, gateways, or system state."""
    pass


class ValidationError(SbrConfigError):
    """Validation found issues that prevent configuration."""
    pass


class ConfigurationError(SbrConfigError):
    """Failed to apply a configuration change."""
    pass


class PersistenceError(SbrConfigError):
    """Failed to write persistent configuration."""
    pass


class RollbackError(SbrConfigError):
    """Failed to restore previous state."""
    pass


class PrivilegeError(SbrConfigError):
    """Insufficient privileges (not root)."""
    pass


class LockError(SbrConfigError):
    """Could not acquire lock file (another instance running)."""
    pass
