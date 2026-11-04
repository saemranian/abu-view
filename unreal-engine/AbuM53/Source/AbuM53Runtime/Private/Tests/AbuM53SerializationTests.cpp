// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Types.h"
#include "AbuM53AssetVersion.h"
#include "Misc/AutomationTest.h"
#include "Serialization/CustomVersion.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"
#include "Serialization/ObjectAndNameAsStringProxyArchive.h"
#include "UObject/Class.h"

#if WITH_DEV_AUTOMATION_TESTS
namespace
{
FAbuM53Frame MakeSerializationFrame(int32 Count)
{
    FAbuM53Frame Frame;
    Frame.TimeSeconds = 12.5;
    Frame.SplatCount = Count;
    Frame.SHDegree = 3;
    Frame.SourceOrigin = FVector(12345, -54321, 0.25);
    Frame.SourceBounds = FBox(FVector(-1, -2, -3), FVector(4, 5, 6));
    Frame.SourceCoordinateProfile = TEXT("right_up_back");
    Frame.bSourceAntialiased = true;
    Frame.PackedPoints.SetNumUninitialized(Count * sizeof(FAbuM53GPUPoint));
    for (int32 I = 0; I < Frame.PackedPoints.Num(); ++I) Frame.PackedPoints[I] = static_cast<uint8>((I * 31) % 251);
    return Frame;
}

class FAbuM53CountingWriter : public FMemoryWriter
{
public:
    explicit FAbuM53CountingWriter(TArray<uint8>& Bytes) : FMemoryWriter(Bytes, true) {}
    void Serialize(void* Data, int64 Length) override
    {
        ++Calls;
        LargestWrite = FMath::Max(LargestWrite, Length);
        FMemoryWriter::Serialize(Data, Length);
    }
    int32 Calls = 0;
    int64 LargestWrite = 0;
};
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53ContiguousSerializationTest,
    "AbuM53.Runtime.Serialization.ContiguousRoundTrip",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FAbuM53ContiguousSerializationTest::RunTest(const FString& Parameters)
{
    FAbuM53Frame Source = MakeSerializationFrame(4096);
    TArray<uint8> Bytes;
    FAbuM53CountingWriter Writer(Bytes);
    FAbuM53Frame::StaticStruct()->SerializeItem(Writer, &Source, nullptr);
    TestFalse(TEXT("native save succeeds"), Writer.IsError());
    TestTrue(TEXT("package declares its frame format"), Writer.GetCustomVersions().GetVersion(FAbuM53AssetVersion::GUID) != nullptr);
    TestEqual(TEXT("point payload is written as one contiguous block"), Writer.LargestWrite, static_cast<int64>(Source.PackedPoints.Num()));
    TestTrue(TEXT("write call count is independent of the number of payload bytes"), Writer.Calls < 100);

    FMemoryReader Reader(Bytes, true);
    Reader.SetCustomVersions(Writer.GetCustomVersions());
    FAbuM53Frame Loaded;
    FAbuM53Frame::StaticStruct()->SerializeItem(Reader, &Loaded, nullptr);
    TestFalse(TEXT("native load succeeds"), Reader.IsError());
    TestEqual(TEXT("sample time survives"), Loaded.TimeSeconds, Source.TimeSeconds);
    TestEqual(TEXT("count survives"), Loaded.SplatCount, Source.SplatCount);
    TestEqual(TEXT("SH degree survives"), Loaded.SHDegree, Source.SHDegree);
    TestEqual(TEXT("origin survives"), Loaded.SourceOrigin, Source.SourceOrigin);
    TestTrue(TEXT("bounds survive"), Loaded.SourceBounds.Equals(Source.SourceBounds));
    TestEqual(TEXT("coordinate metadata survives"), Loaded.SourceCoordinateProfile, Source.SourceCoordinateProfile);
    TestTrue(TEXT("antialias metadata survives"), Loaded.bSourceAntialiased);
    TestTrue(TEXT("all payload bytes survive without conversion or loss"), Loaded.PackedPoints == Source.PackedPoints);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53LegacySerializationTest,
    "AbuM53.Runtime.Serialization.LegacyTaggedMigration",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FAbuM53LegacySerializationTest::RunTest(const FString& Parameters)
{
    FAbuM53Frame Source = MakeSerializationFrame(2);
    TArray<uint8> Bytes;
    FMemoryWriter MemoryWriter(Bytes, true);
    FObjectAndNameAsStringProxyArchive Writer(MemoryWriter, false);
    // Exactly the old struct contract: reflected fields, without the new custom version.
    FAbuM53Frame::StaticStruct()->SerializeTaggedProperties(Writer, reinterpret_cast<uint8*>(&Source), FAbuM53Frame::StaticStruct(), nullptr);
    TestFalse(TEXT("legacy fixture saved"), Writer.IsError());
    TestTrue(TEXT("legacy fixture has no new format version"), Writer.GetCustomVersions().GetVersion(FAbuM53AssetVersion::GUID) == nullptr);
    FMemoryReader MemoryReader(Bytes, true);
    FObjectAndNameAsStringProxyArchive Reader(MemoryReader, false);
    Reader.SetCustomVersions(Writer.GetCustomVersions());
    FAbuM53Frame Loaded;
    FAbuM53Frame::StaticStruct()->SerializeItem(Reader, &Loaded, nullptr);
    TestFalse(TEXT("new serializer accepts old tagged data"), Reader.IsError());
    TestEqual(TEXT("legacy count survives"), Loaded.SplatCount, Source.SplatCount);
    TestEqual(TEXT("legacy origin survives"), Loaded.SourceOrigin, Source.SourceOrigin);
    TestEqual(TEXT("legacy profile survives"), Loaded.SourceCoordinateProfile, Source.SourceCoordinateProfile);
    TestTrue(TEXT("legacy payload survives"), Loaded.PackedPoints == Source.PackedPoints);
    TArray<uint8> Upgraded;
    FAbuM53CountingWriter UpgradeWriter(Upgraded);
    FAbuM53Frame::StaticStruct()->SerializeItem(UpgradeWriter, &Loaded, nullptr);
    TestFalse(TEXT("legacy frame upgrades on its next save"), UpgradeWriter.IsError());
    TestEqual(TEXT("upgraded payload uses a block write"), UpgradeWriter.LargestWrite, static_cast<int64>(Source.PackedPoints.Num()));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53SerializationValidationTest,
    "AbuM53.Runtime.Serialization.MalformedPayload",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FAbuM53SerializationValidationTest::RunTest(const FString& Parameters)
{
    FAbuM53Frame Source = MakeSerializationFrame(1);
    TArray<uint8> Bytes;
    FMemoryWriter Writer(Bytes, true);
    Source.Serialize(Writer);
    for (const int32 BadCount : {-1, 2, MAX_int32})
    {
        TArray<uint8> Corrupt = Bytes;
        FMemory::Memcpy(Corrupt.GetData() + sizeof(uint32) + sizeof(double), &BadCount, sizeof(BadCount));
        FMemoryReader Reader(Corrupt, true);
        Reader.SetCustomVersions(Writer.GetCustomVersions());
        FAbuM53Frame Loaded;
        Loaded.Serialize(Reader);
        TestTrue(TEXT("invalid count rejects the archive"), Reader.IsError());
        TestEqual(TEXT("invalid count never allocates the payload"), Loaded.PackedPoints.Num(), 0);
    }
    Bytes.SetNum(Bytes.Num() - 1);
    FMemoryReader Truncated(Bytes, true);
    Truncated.SetCustomVersions(Writer.GetCustomVersions());
    FAbuM53Frame Loaded;
    Loaded.Serialize(Truncated);
    TestTrue(TEXT("truncated payload rejects the archive"), Truncated.IsError());
    TestEqual(TEXT("truncation is detected before allocation"), Loaded.PackedPoints.Num(), 0);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53TransientSerializationTest,
    "AbuM53.Runtime.Serialization.TransientAndExternalIndex",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FAbuM53TransientSerializationTest::RunTest(const FString& Parameters)
{
    FAbuM53Frame Source = MakeSerializationFrame(1);
    TArray<uint8> Bytes;
    FMemoryWriter MemoryWriter(Bytes);
    FObjectAndNameAsStringProxyArchive Writer(MemoryWriter, false);
    FAbuM53Frame::StaticStruct()->SerializeItem(Writer, &Source, nullptr);
    FMemoryReader MemoryReader(Bytes);
    FObjectAndNameAsStringProxyArchive Reader(MemoryReader, false);
    Reader.SetCustomVersions(Writer.GetCustomVersions());
    FAbuM53Frame Loaded;
    FAbuM53Frame::StaticStruct()->SerializeItem(Reader, &Loaded, nullptr);
    TestFalse(TEXT("nonpersistent reflected round-trip succeeds"), Reader.IsError());
    TestTrue(TEXT("nonpersistent payload is preserved"), Loaded.PackedPoints == Source.PackedPoints);

    FAbuM53Frame Index;
    Index.ExternalFilename = TEXT("frames/frame_0001.ply");
    Index.TimeSeconds = 0.5;
    TArray<uint8> IndexBytes;
    FMemoryWriter IndexWriter(IndexBytes, true);
    Index.Serialize(IndexWriter);
    FMemoryReader IndexReader(IndexBytes, true);
    IndexReader.SetCustomVersions(IndexWriter.GetCustomVersions());
    FAbuM53Frame LoadedIndex;
    LoadedIndex.Serialize(IndexReader);
    TestFalse(TEXT("external frame index round-trip succeeds"), IndexReader.IsError());
    TestEqual(TEXT("external path survives"), LoadedIndex.ExternalFilename, Index.ExternalFilename);
    TestEqual(TEXT("external frame index has no embedded bytes"), LoadedIndex.PackedPoints.Num(), 0);
    return true;
}
#endif
