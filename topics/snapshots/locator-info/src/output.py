from typing import List
from datetime import datetime
from json import dumps
from dataclasses import asdict
from tabulate import tabulate

from .stow import are_stow_versions_supported
from .data import SnapLayer, construct_data_from_raw, Data
from .common import RawDataContainerType, warn_bad_data


def display_data(raw_data: RawDataContainerType, verbose: bool, json: bool) -> None:
    """Process the raw spec file data and display it in a relevant and readable manner"""
    data = construct_data_from_raw(raw_data)

    if not _validate_stow_versions_supported(data):
        warn_bad_data("Some of the objects' versioning is not supported by the script yet")

    if json:
        print(dumps(asdict(data)))
        return

    _print_data_nicely(data, verbose)


def _print_data_nicely(data: Data, verbose: bool) -> None:
    guids = [layer.guid for layer in data.snap_layers]
    guids.append(str(data.guid))
    unique_guids = set(guids)

    print(f"Filesystem name: {data.fs_name}")
    print(f"Snapshot name: {data.snapshot_name}")
    print(f"Original filesystem id: {data.orig_fq_fs_id}")
    print(f"Number of snap layers: {data.num_layers}")

    if verbose:
        print("\nSnap layers:")
        print(_snaplayers_table(data.snap_layers))
        print(f"\nUnique GUIDs: {unique_guids}")
    else:
        print(f"Uploader cluster GUID: {data.guid}", end="")
        if len(unique_guids) > 1:
            print(f". With {len(unique_guids)-1} other unique cluster GUIDs, use --verbose for more info")
        else:
            print()

    print(f"Compatible weka versions: {data.weka_download_compatability}")
    print(f"Capacity: {data.capacity.pretty_str()}")


def _snaplayers_table(snap_layers: List[SnapLayer]) -> str:
    headers = [
        "ID",
        "GUID",
        "Original ID",
        "No. Buckets",
        "UTC Freeze Date",
        "Capacity: metadata",
        "Capacity: data",
        "Uploading Cluster Version",
    ]
    values = [
        [
            layer.id,
            layer.guid,
            layer.orig_fq_snap_layer_id,
            layer.buckets_num,
            datetime.utcfromtimestamp(layer.freeze_timestamp),
            layer.capacity.metadata(),
            layer.capacity.data(),
            layer.weka_upload_range,
        ]
        for layer in snap_layers
    ]
    return tabulate(values, headers)


def _validate_stow_versions_supported(data: Data) -> bool:
    unique_stow_versions = {layer.stow_version for layer in data.snap_layers} | {data.stow_version}
    return are_stow_versions_supported(*unique_stow_versions)
