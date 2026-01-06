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
    freeze_timestamp: int  # unix timestamp
    capacity: Capacity
    weka_upload_range: str
    orig_fq_snap_layer_id: str


@dataclass
class Data:
    """An organized and relevant view into the raw spec file data"""

    stow_version: StowVersionType
    guid: str
    fs_id: int
    snap_view_id: int
    fs_name: str
    snapshot_name: str
    access_point: str
    attachment_point: str
    attachment_point_depth: int
    fs_ssd_capacity: int
    fs_total_capacity: int
    fs_max_files: int
    orig_fq_fs_id: str
    capacity: Capacity
    num_layers: int
    weka_download_compatability: str
    snap_layers: list[SnapLayer]


def construct_data_from_raw(raw_data: RawDataContainerType) -> Data:
    snap_layers = [
        SnapLayer(
            id=layer.snapLayerId,
            guid=str(layer.guid),
            stow_version=layer.stowVersion,
            buckets_num=layer.bucketsNum,
            freeze_timestamp=layer.freezeTimestamp.secs,
            capacity=Capacity(
                metadata_bytes=blocks_to_bytes(layer.capacity.metadata),
                data_bytes=blocks_to_bytes(layer.capacity.data),
            ),
            weka_upload_range=uploader_version_range(layer.stowVersion),
            orig_fq_snap_layer_id=fq_snap_layer_id_string(layer.origFqSnapLayerId),
        )
        for layer in raw_data.snapLayers
    ]

    stow_versions = [layer.stow_version for layer in snap_layers]
    stow_versions.append(raw_data.stowVersion)

    return Data(
        capacity=Capacity(
            metadata_bytes=blocks_to_bytes(sum(layer.capacity.metadata for layer in raw_data.snapLayers)),
            data_bytes=blocks_to_bytes(sum(layer.capacity.data for layer in raw_data.snapLayers)),
        ),
        weka_download_compatability=download_compatability(min(stow_versions), max(stow_versions)),
        num_layers=raw_data.snapLayersNum,
        stow_version=raw_data.stowVersion,
        guid=raw_data.guid,
        fs_id=raw_data.fsId,
        snap_view_id=raw_data.snapViewId,
        fs_name=raw_data.fsName,
        snapshot_name=raw_data.snapshotName,
        access_point=raw_data.accessPoint,
        attachment_point=fq_snap_layer_id_string(raw_data.attachmentPoint),
        attachment_point_depth=raw_data.attachmentPointDepth,
        fs_ssd_capacity=blocks_to_bytes(raw_data.fsRequestedSSDBudget),
        fs_total_capacity=blocks_to_bytes(raw_data.fsTotalBudget),
        fs_max_files=raw_data.fsMaxFiles,
        orig_fq_fs_id=fq_fs_id_string(raw_data.origFqFSId),
        snap_layers=snap_layers,
    )


def blocks_to_bytes(blocks):
    if blocks is None:
        return None
    return blocks * BLOCK_TO_BYTES


def fq_snap_layer_id_string(fq_snap_layer_id):
    if fq_snap_layer_id is None:
        return ""
    return f"{fq_snap_layer_id.guid}:{fq_snap_layer_id.snapLayerId}"


def fq_fs_id_string(fq_fs_id):
    if fq_fs_id is None:
        return ""
    return f"{fq_fs_id.guid}:{fq_fs_id.fsId}"
