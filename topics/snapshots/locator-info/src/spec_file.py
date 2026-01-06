import construct as c
from uuid import UUID

from .common import warn_bad_data, StowVersionType, CustomException, RawDataContainerType


class SpecFile:
    """Definitions and utils for deserialization of a binary a spec file into a an object"""

    StowVersion = c.Int32ul

    InodeId = c.Int64ul
    EncryptionVersion = c.Int8ul
    GenericWrappedFilesystemKey = c.Bytes(256)  # we don't care about its value or structure

    FSId = c.Int32ul
    SnapViewId = c.Int32ul
    SnapLayerId = c.Int32ul
    SnapLayerStowGeneration = c.Int32ul
    SnapDepth = c.Int32ul
    XUUID = c.ExprSymmetricAdapter(c.Bytes(16), lambda obj, context: UUID(bytes=obj).hex)
    BlocksCount = c.Int64sl
    StowCapacity = c.Struct("metadata" / BlocksCount, "data" / BlocksCount)
    Seconds = c.Int64ul
    NanoSecs = c.Int32ul
    Timestamp = c.Struct("secs" / Seconds, "nanosecs" / NanoSecs)
    FQSnapLayerId = c.Struct("guid" / XUUID, "snapLayerId" / SnapLayerId)
    FixedString8 = c.PascalString(c.Int8ul, "utf8")
    FixedString16 = c.PascalString(c.Int16ul, "utf8")
    FixedString64 = c.PascalString(c.Int64ul, "utf8")
    FQFSId = c.Struct("guid" / XUUID, "fsId" / FSId)
    KmsType = c.Bytes(1)

    def __init__(self, spec_file_path: str):
        self.path = spec_file_path
        self.file_stow_version = self.StowVersion.parse_file(self.path)

        def _versioned_con(min_version: StowVersionType, con: c.Construct) -> c.Construct:
            return c.If(self.file_stow_version >= min_version, con)

        self.StowedSnapLayer = c.Struct(
            "snapLayerId" / self.SnapLayerId,
            "generation" / _versioned_con(1, self.SnapLayerStowGeneration),
            "depth" / _versioned_con(2, self.SnapDepth),
            "isForked" / _versioned_con(7, c.Flag),
            "squashDepth" / _versioned_con(7, self.SnapDepth),
            "guid" / self.XUUID,
            "capacity" / self.StowCapacity,
            "bucketsNum" / c.Int16ul,
            "mtimeFallback" / self.Timestamp,
            "indexInParent_deprecated" / c.Int8ul,
            "stowVersion" / self.StowVersion,
            "freezeTimestamp" / _versioned_con(9, self.Timestamp),
            "origFqSnapLayerId" / _versioned_con(9, self.FQSnapLayerId),
            "origLastMergedParent" / _versioned_con(9, self.FQSnapLayerId),
        )
        self.StowSpec = c.Struct(
            "stowVersion" / self.StowVersion,
            "rootInodeId" / self.InodeId,
            "encryptionSchemeVersion" / _versioned_con(1, self.EncryptionVersion),
            c.If(self.file_stow_version == 1, c.Bytes(77)),
            c.If(self.file_stow_version == 1, self.FixedString64),
            _versioned_con(2, self.GenericWrappedFilesystemKey),  # wrappedFilesystemKey
            "guid" / _versioned_con(9, self.XUUID),
            "fsId" / _versioned_con(9, self.FSId),
            "snapViewId" / _versioned_con(9, self.SnapViewId),
            "fsName" / _versioned_con(9, self.FixedString8),
            "snapshotName" / _versioned_con(9, self.FixedString8),
            "accessPoint" / _versioned_con(9, self.FixedString8),
            "fsRequestedSSDBudget" / _versioned_con(9, self.BlocksCount),
            "fsTotalBudget" / _versioned_con(9, self.BlocksCount),
            "fsMaxFiles" / _versioned_con(9, c.Int64ul),
            "origFqFSId" / _versioned_con(9, self.FQFSId),
            "customizationKmsType" / _versioned_con(11, self.KmsType),
            "kmsKeyName" / _versioned_con(11, self.FixedString8),
            "kmsNamespace" / _versioned_con(11, self.FixedString16),
            "attachmentPoint" / _versioned_con(14, self.FQSnapLayerId),
            "attachmentPointDepth" / _versioned_con(14, self.SnapDepth),
            "snapLayersNum" / c.Int64ul,
            "snapLayers" / c.Array(c.this.snapLayersNum, self.StowedSnapLayer),
            "excessiveBytesIndication" / c.GreedyBytes,
        )

    def deserialize(self) -> RawDataContainerType:
        try:
            res: RawDataContainerType = self.StowSpec.parse_file(self.path)
        except Exception as ex:
            raise CustomException(
                "Encountered an error while parsing the file,"
                f" make sure it contains a valid spec and was not tempered with. Original parsing error: {ex}"
            ) from ex

        if len(res.excessiveBytesIndication) != 0:
            warn_bad_data("Spec file contains extra data that the script does not know how to handle")

        for layer in res.snapLayers:
            if layer.freezeTimestamp is None:
                layer.freezeTimestamp = layer.mtimeFallback

            if layer.origFqSnapLayerId is None:
                layer.origFqSnapLayerId = c.Container(guid=layer.guid, snapLayerId=layer.snapLayerId)

        if res.guid is None:
            res.guid = res.snapLayers[-1].guid

        return res
