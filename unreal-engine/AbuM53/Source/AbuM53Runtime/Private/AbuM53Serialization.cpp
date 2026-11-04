// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Types.h"
#include "AbuM53AssetVersion.h"
#include "Serialization/CustomVersion.h"

const FGuid FAbuM53AssetVersion::GUID(0x8CB97329, 0xAF014F42, 0x8A4EA70E, 0x2C1368DF);
static FCustomVersionRegistration GAbuM53AssetVersion(
    FAbuM53AssetVersion::GUID, FAbuM53AssetVersion::LatestVersion, TEXT("AbuM53AssetVersion"));

bool FAbuM53Frame::Serialize(FArchive& Ar)
{
    // Transactions, duplication, reference collection and text exports keep UE's
    // reflected serialization contract. Their archive version containers are not
    // package headers and must not be mistaken for the persistent format.
    if (!Ar.IsPersistent() || Ar.IsTextFormat() || !(Ar.IsLoading() || Ar.IsSaving())) return false;

    Ar.UsingCustomVersion(FAbuM53AssetVersion::GUID);
    const int32 Version = Ar.CustomVer(FAbuM53AssetVersion::GUID);
    // Returning false makes UScriptStruct read the original tagged properties,
    // including PackedPoints. Saving that asset upgrades it on its next save.
    if (Ar.IsLoading() && Version < FAbuM53AssetVersion::ContiguousFramePayload) return false;
    if (Version != FAbuM53AssetVersion::LatestVersion)
    {
        Ar.SetError();
        return true;
    }

    constexpr uint32 FrameMagic = 0x4633354D; // "M53F" in the supported little-endian package.
    uint32 Magic = FrameMagic;
    Ar << Magic;
    if (Ar.IsError() || Magic != FrameMagic)
    {
        Ar.SetError();
        return true;
    }
    Ar << TimeSeconds << SplatCount << SHDegree << SourceOrigin << SourceBounds;
    Ar << ExternalFilename << SourceCoordinateProfile << bSourceAntialiased;
    int32 PayloadBytes = PackedPoints.Num();
    Ar << PayloadBytes;

    const int64 ExpectedBytes = static_cast<int64>(SplatCount) * sizeof(FAbuM53GPUPoint);
    const bool bExternalIndex = !ExternalFilename.IsEmpty() && PayloadBytes == 0;
    const bool bValidBounds = !SourceBounds.IsValid ||
        (!SourceBounds.Min.ContainsNaN() && !SourceBounds.Max.ContainsNaN());
    if (Ar.IsError() || SplatCount < 0 || SHDegree < 0 || SHDegree > 3 || PayloadBytes < 0 ||
        (!bExternalIndex && ExpectedBytes != PayloadBytes) ||
        !FMath::IsFinite(TimeSeconds) || SourceOrigin.ContainsNaN() || !bValidBounds)
    {
        if (Ar.IsLoading()) PackedPoints.Reset();
        Ar.SetError();
        return true;
    }

    if (Ar.IsLoading())
    {
        // Reject truncated payloads before allocating. Package readers may return
        // -1 for an unknown total; their Serialize implementation still checks reads.
        const int64 TotalBytes = Ar.TotalSize();
        const int64 Position = Ar.Tell();
        if (TotalBytes >= 0 && Position >= 0 &&
            (Position > TotalBytes || PayloadBytes > TotalBytes - Position))
        {
            PackedPoints.Reset();
            Ar.SetError();
            return true;
        }
        PackedPoints.SetNumUninitialized(PayloadBytes);
    }
    // Reflected TArray<uint8> in an editor package otherwise visits every byte
    // through FByteProperty. This makes serialization proportional to I/O size.
    if (PayloadBytes) Ar.Serialize(PackedPoints.GetData(), PayloadBytes);
    if (Ar.IsLoading() && Ar.IsError()) PackedPoints.Reset();
    return true;
}
