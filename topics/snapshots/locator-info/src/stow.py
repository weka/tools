"""Mapping and validation utils between stow versioning to weka versioning"""

from dataclasses import dataclass, field
from typing import Optional

from .common import StowVersionType

INVALID_COMPATABILITY = "N/A (the script does not support this object's versioning, displayed data might be partial)"


@dataclass
class _WekaCompatabilityRange:
    introduction_ver: str
    deprecation_ver: Optional[str] = field(default=None)


# needs to be kept up to date with weka/config/stow/defs.d
STOW_WEKA_COMP = {
    0: _WekaCompatabilityRange("v3.1.7.1", deprecation_ver="v3.11.0"),
    1: _WekaCompatabilityRange("v3.4.2", deprecation_ver="v3.11.0"),
    2: _WekaCompatabilityRange("v3.5.2"),
    3: _WekaCompatabilityRange("v3.10.0"),
    4: _WekaCompatabilityRange("v3.10.1"),
    5: _WekaCompatabilityRange("v3.11.0"),
    6: _WekaCompatabilityRange("v3.12.0"),
    7: _WekaCompatabilityRange("v3.13.0"),
    8: _WekaCompatabilityRange("v3.14.0"),
    9: _WekaCompatabilityRange("v3.15.0"),
}


def are_stow_versions_supported(*stow_versions: StowVersionType) -> bool:
    return all(stow_version in STOW_WEKA_COMP for stow_version in stow_versions)


def download_compatability(min_stow_version: StowVersionType, max_stow_version: StowVersionType) -> str:
    """Weka version range in which it's possible to download a spec file with the given min and max stow versions"""
    if not are_stow_versions_supported(min_stow_version, max_stow_version):
        return INVALID_COMPATABILITY
    min_ver = STOW_WEKA_COMP[max_stow_version].introduction_ver
    deprecation_ver = STOW_WEKA_COMP[min_stow_version].deprecation_ver
    if deprecation_ver is None:
        return f"{min_ver}+"
    return f"{min_ver}..{deprecation_ver}"


def uploader_version_range(stow_version: StowVersionType) -> str:
    """Weka version range in which the stow version could have been uploaded"""
    if not are_stow_versions_supported(stow_version):
        return INVALID_COMPATABILITY
    if stow_version + 1 not in STOW_WEKA_COMP:
        return f"{STOW_WEKA_COMP[stow_version].introduction_ver}+"
    return f"{STOW_WEKA_COMP[stow_version].introduction_ver}..{STOW_WEKA_COMP[stow_version+1].introduction_ver}"
