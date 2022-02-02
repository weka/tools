"""Structures for holding the spec file data in a more readable, organized and relevant manner"""

from dataclasses import dataclass
from typing import List
from humanize import naturalsize

from .stow import uploader_version_range, download_compatability
from .common import StowVersionType, RawDataContainerType

BLOCK_TO_BYTES = 4 * 1024


@dataclass
class Capacity:
    metadata_bytes: int
    data_bytes: int

    def metadata(self) -> str:
        return naturalsize(self.metadata_bytes)

    def data(self) -> str:
        return naturalsize(self.data_bytes)

    def total(self) -> str:
        return naturalsize(self.data_bytes + self.metadata_bytes)

    def pretty_str(self) -> str:
        return f"metadata: {self.metadata()}, data: {self.data()}, total: {self.total()}"


@dataclass
class SnapLayer:
    id: int
    guid: str
    stow_version: StowVersionType
    buckets_num: int
    unix_time: int
    capacity: Capacity
    weka_upload_range: str


@dataclass
class Data:
    """An organized and relevant view into the raw spec file data"""

    stow_version: StowVersionType
    capacity: Capacity
    num_layers: int
    weka_download_compatability: str
    snap_layers: List[SnapLayer]


def construct_data_from_raw(raw_data: RawDataContainerType) -> Data:
    snap_layers = [
        SnapLayer(
            id=layer.snapLayerId,
            guid=str(layer.guid),
            stow_version=layer.stowVersion,
            buckets_num=layer.bucketsNum,
            unix_time=layer.timestamp.secs,
            capacity=Capacity(
                metadata_bytes=layer.capacity.metadata * BLOCK_TO_BYTES,
                data_bytes=layer.capacity.data * BLOCK_TO_BYTES,
            ),
            weka_upload_range=uploader_version_range(layer.stowVersion),
        )
        for layer in raw_data.snapLayers
    ]

    stow_versions = [layer.stow_version for layer in snap_layers]

    return Data(
        capacity=Capacity(
            metadata_bytes=sum(layer.capacity.metadata for layer in raw_data.snapLayers) * BLOCK_TO_BYTES,
            data_bytes=sum(layer.capacity.data for layer in raw_data.snapLayers) * BLOCK_TO_BYTES,
        ),
        weka_download_compatability=download_compatability(min(stow_versions), max(stow_versions)),
        num_layers=raw_data.snapLayersNum,
        stow_version=raw_data.stowVersion,
        snap_layers=snap_layers,
    )
