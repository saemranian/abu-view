// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Types.h"
#include "AbuM53/Core.h"
#include "AbuM53Compression.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformFileManager.h"
#include <algorithm>
#include <cmath>
#include <cfloat>

namespace
{
bool IsImportCanceled(const FAbuM53ImportFeedback* Feedback, FString& Error)
{
    if (Feedback && Feedback->ShouldCancel && Feedback->ShouldCancel())
    {
        Error = TEXT("Import canceled.");
        return true;
    }
    return false;
}

void ReportImportProgress(const FAbuM53ImportFeedback* Feedback, const FString& Message)
{
    if (Feedback && Feedback->ReportProgress) Feedback->ReportProgress(Message);
}

bool LoadFrame(const FString& Filename, double Time, bool bStableIds, FAbuM53Frame& Frame,
    FString& Error, int64& RemainingBytes, const FAbuM53ImportFeedback* Feedback)
{
    if (IsImportCanceled(Feedback, Error)) return false;
    if (RemainingBytes < static_cast<int64>(sizeof(FAbuM53GPUPoint)))
    {
        Error = TEXT("Decoded memory budget exhausted; split the sequence into smaller clips.");
        return false;
    }
    abum53::LoadOptions Options;
    Options.maxSplats = FMath::Min<int64>(20000000, RemainingBytes / sizeof(FAbuM53GPUPoint));
    Options.maxBytes = FMath::Max<uint64_t>(64ull*1024*1024,static_cast<uint64_t>(RemainingBytes)*2);
    Options.decompress=&AbuM53Decompress;
    if (Feedback && Feedback->ShouldCancel) Options.shouldCancel = [Feedback]() { return Feedback->ShouldCancel(); };
    abum53::Cloud Cloud;
    std::string CoreError;
    ReportImportProgress(Feedback, FString::Printf(TEXT("Reading %s"), *FPaths::GetCleanFilename(Filename)));
    const double DecodeStarted = FPlatformTime::Seconds();
    if (!abum53::LoadFile(std::filesystem::path(*Filename), Cloud, CoreError, Options))
    {
        Error = FString::Printf(TEXT("%s: %s"), *Filename, UTF8_TO_TCHAR(CoreError.c_str()));
        return false;
    }
    const double DecodeSeconds = FPlatformTime::Seconds() - DecodeStarted;
    if (IsImportCanceled(Feedback, Error)) return false;
    if (Cloud.splats.empty() || Cloud.splats.size() > static_cast<size_t>(MAX_int32 / sizeof(FAbuM53GPUPoint)))
    {
        Error = TEXT("Empty cloud or frame exceeds the supported packed-array size.");
        return false;
    }
    if (bStableIds)
    {
        std::sort(Cloud.splats.begin(), Cloud.splats.end(), [](const auto& A, const auto& B) { return A.id < B.id; });
        for (size_t I=1; I<Cloud.splats.size(); ++I)
        {
            if ((I & 4095) == 0 && IsImportCanceled(Feedback, Error)) return false;
            if (Cloud.splats[I-1].id == Cloud.splats[I].id)
            {
                Error = TEXT("Stable-ID source contains duplicate Gaussian IDs.");
                return false;
            }
        }
    }
    Frame.TimeSeconds = Time;
    Frame.SplatCount = static_cast<int32>(Cloud.splats.size());
    Frame.SHDegree = Cloud.shDegree;
    Frame.SourceCoordinateProfile=Cloud.coordinates==abum53::Coordinates::RUB ? TEXT("right_up_back") : TEXT("unspecified");
    Frame.bSourceAntialiased=Cloud.antialiased;
    Frame.SourceBounds = FBox(ForceInit);
    ReportImportProgress(Feedback, FString::Printf(TEXT("Preparing bounds for %s (%d splats)"), *FPaths::GetCleanFilename(Filename), Frame.SplatCount));
    int32 BoundsIndex = 0;
    for (const auto& Point : Cloud.splats)
    {
        if ((BoundsIndex++ & 4095) == 0 && IsImportCanceled(Feedback, Error)) return false;
        const FVector Position(Point.position[0]+Cloud.origin[0], Point.position[1]+Cloud.origin[1], Point.position[2]+Cloud.origin[2]);
        const double Extent = 3.0 * FMath::Max3(Point.scale[0], Point.scale[1], Point.scale[2]);
        Frame.SourceBounds += Position - FVector(Extent);
        Frame.SourceBounds += Position + FVector(Extent);
    }
    Frame.SourceOrigin = Frame.SourceBounds.GetCenter();
    if (Frame.SourceOrigin.ContainsNaN())
    {
        Error = TEXT("Source coordinates cannot be represented by a finite UE origin.");
        return false;
    }
    const int64 RequiredBytes = static_cast<int64>(Frame.SplatCount) * sizeof(FAbuM53GPUPoint);
    if (RequiredBytes > RemainingBytes)
    {
        Error = TEXT("Decoded frame exceeds remaining import memory budget.");
        return false;
    }
    ReportImportProgress(Feedback, FString::Printf(TEXT("Packing %s (%d splats)"), *FPaths::GetCleanFilename(Filename), Frame.SplatCount));
    if (IsImportCanceled(Feedback, Error)) return false;
    Frame.PackedPoints.SetNumUninitialized(static_cast<int32>(RequiredBytes));
    for (int32 I=0; I<Frame.SplatCount; ++I)
    {
        if ((I & 4095) == 0 && IsImportCanceled(Feedback, Error)) return false;
        const auto& Input = Cloud.splats[I];
        FAbuM53GPUPoint Point;
        Point.PositionOpacity = FVector4f(
            static_cast<float>(Input.position[0]+Cloud.origin[0]-Frame.SourceOrigin.X),
            static_cast<float>(Input.position[1]+Cloud.origin[1]-Frame.SourceOrigin.Y),
            static_cast<float>(Input.position[2]+Cloud.origin[2]-Frame.SourceOrigin.Z), Input.opacity);
        Point.ScaleDegree = FVector4f(Input.scale[0], Input.scale[1], Input.scale[2], static_cast<float>(Cloud.shDegree));
        if (!FMath::IsFinite(Point.PositionOpacity.X) || !FMath::IsFinite(Point.PositionOpacity.Y) || !FMath::IsFinite(Point.PositionOpacity.Z))
        {
            Error = TEXT("Source span exceeds rebased float32 representation; partition it into smaller spatial assets.");
            return false;
        }
        Point.Rotation = FVector4f(Input.rotation[0], Input.rotation[1], Input.rotation[2], Input.rotation[3]);
        FMemory::Memcpy(Point.SH, Input.sh, sizeof(Input.sh));
        FMemory::Memcpy(&Point.Metadata.X, &Input.id, sizeof(Input.id));
        Point.Metadata.Z=Cloud.antialiased ? 1.f : 0.f;
        FMemory::Memcpy(Frame.PackedPoints.GetData()+static_cast<int64>(I)*sizeof(Point), &Point, sizeof(Point));
    }
    RemainingBytes -= RequiredBytes;
    UE_LOG(LogTemp, Display, TEXT("Abu M53 import: %s; %d splats; read %.3f s; bounds/packing %.3f s; %lld packed bytes."),
        *FPaths::GetCleanFilename(Filename), Frame.SplatCount, DecodeSeconds,
        FPlatformTime::Seconds() - DecodeStarted - DecodeSeconds, RequiredBytes);
    return true;
}

bool SafeRelativePath(const FString& Root, const FString& Relative, FString& Absolute)
{
    if (Relative.IsEmpty() || !FPaths::IsRelative(Relative) || Relative.Contains(TEXT(":"))) return false;
    Absolute = FPaths::ConvertRelativePathToFull(FPaths::Combine(Root, Relative));
    FPaths::NormalizeFilename(Absolute);
    FPaths::CollapseRelativeDirectories(Absolute);
    FString Prefix = FPaths::ConvertRelativePathToFull(Root);
    FPaths::NormalizeFilename(Prefix);
    if (!Prefix.EndsWith(TEXT("/"))) Prefix += TEXT("/");
    if (!Absolute.StartsWith(Prefix, ESearchCase::IgnoreCase)) return false;
    // Resolve junctions/symlinks too: lexical containment alone is not sufficient.
    std::error_code Error;
    const auto CanonicalRoot=std::filesystem::weakly_canonical(std::filesystem::path(*Root),Error);
    if (Error) return false;
    const auto CanonicalFile=std::filesystem::weakly_canonical(std::filesystem::path(*Absolute),Error);
    if (Error) return false;
    FString RealRoot(CanonicalRoot.wstring().c_str());
    FString RealFile(CanonicalFile.wstring().c_str());
    FPaths::NormalizeFilename(RealRoot);
    FPaths::NormalizeFilename(RealFile);
    if (!RealRoot.EndsWith(TEXT("/"))) RealRoot+=TEXT("/");
    return RealFile.StartsWith(RealRoot, ESearchCase::IgnoreCase);
}

bool EqualIds(const FAbuM53Frame& A, const FAbuM53Frame& B)
{
    if (A.SplatCount != B.SplatCount || A.SHDegree != B.SHDegree) return false;
    for (int32 I=0; I<A.SplatCount; ++I)
    {
        const int64 Offset = static_cast<int64>(I)*sizeof(FAbuM53GPUPoint)+STRUCT_OFFSET(FAbuM53GPUPoint, Metadata);
        if (FMemory::Memcmp(A.PackedPoints.GetData()+Offset, B.PackedPoints.GetData()+Offset, sizeof(uint64)) != 0) return false;
    }
    return true;
}
}

static bool DecodeFileImpl(const FString& Filename, FAbuM53ImportResult& Result, FString& Error, int64 MaxDecodedBytes, bool bIndexOnly,
    const FAbuM53ImportFeedback* Feedback)
{
    Error.Reset();
    if (IsImportCanceled(Feedback, Error)) return false;
    FAbuM53ImportResult Working;
    Working.SourceFilename = FPaths::ConvertRelativePathToFull(Filename);
    int64 RemainingBytes = FMath::Clamp<int64>(MaxDecodedBytes, 256, MAX_int32);
    const int64 OriginalBudget = RemainingBytes;
    const FString Extension = FPaths::GetExtension(Filename).ToLower();
    if (Extension != TEXT("am53seq") && Extension != TEXT("json"))
    {
        if (bIndexOnly) { Error=TEXT("Streaming index requires an .am53seq or supported JSON manifest."); return false; }
        FAbuM53Frame Frame;
        if (!LoadFrame(Working.SourceFilename, 0, false, Frame, Error, RemainingBytes, Feedback)) return false;
        if (Frame.SourceCoordinateProfile!=TEXT("unspecified")) Working.CoordinateProfile=Frame.SourceCoordinateProfile;
        Working.Frames.Add(MoveTemp(Frame));
    }
    else
    {
        const int64 JsonBytes = FPlatformFileManager::Get().GetPlatformFile().FileSize(*Working.SourceFilename);
        if (JsonBytes < 0 || JsonBytes > 16*1024*1024)
        {
            Error = TEXT("Sequence manifest is missing or larger than 16 MiB."); return false;
        }
        FString Text;
        TSharedPtr<FJsonObject> Document;
        if (!FFileHelper::LoadFileToString(Text, *Working.SourceFilename) ||
            !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Document) || !Document.IsValid())
        {
            Error = TEXT("Invalid sequence JSON."); return false;
        }
        double Schema = 0;
        if (!Document->TryGetNumberField(TEXT("schema"), Schema) || Schema != 1)
        {
            Error = TEXT("Only sequence schema 1 is supported."); return false;
        }
        if (Document->HasField(TEXT("storage")))
        {
            FString Storage;
            if (!Document->TryGetStringField(TEXT("storage"), Storage) ||
                (Storage != TEXT("embedded") && Storage != TEXT("external")))
            {
                Error = TEXT("Sequence storage must be embedded or external."); return false;
            }
            // Explicit opt-in keeps the default self-contained asset contract.
            // This same path is used by the editor factory, reimport and runtime.
            if (Storage == TEXT("external")) bIndexOnly = true;
        }
        FString Type;
        if (!Document->TryGetStringField(TEXT("sequence_type"), Type) ||
            (Type != TEXT("independent_3dgs_frames") && Type != TEXT("stable_id_keyframes")))
        {
            Error = TEXT("sequence_type must be independent_3dgs_frames or stable_id_keyframes."); return false;
        }
        Working.bStableIds = Type == TEXT("stable_id_keyframes");
        if (bIndexOnly && Working.bStableIds)
        {
            Error=TEXT("External streaming currently supports independent frames. Import stable-ID clips as embedded assets."); return false;
        }
        bool DeclaredStableIds = false;
        Document->TryGetBoolField(TEXT("stable_ids"), DeclaredStableIds);
        if (Working.bStableIds && !DeclaredStableIds)
        {
            Error = TEXT("Stable-ID keyframes require stable_ids:true and AM53 sources with matching IDs."); return false;
        }
        Document->TryGetStringField(TEXT("coordinate_frame"), Working.CoordinateProfile);
        if (Document->HasField(TEXT("fps")) && (!Document->TryGetNumberField(TEXT("fps"), Working.FramesPerSecond) ||
            !FMath::IsFinite(Working.FramesPerSecond) || Working.FramesPerSecond <= 0 || Working.FramesPerSecond > 10000))
        {
            Error = TEXT("fps must be a finite number in (0,10000]."); return false;
        }
        const TArray<TSharedPtr<FJsonValue>>* JsonFrames = nullptr;
        if (!Document->TryGetArrayField(TEXT("frames"), JsonFrames) || !JsonFrames || JsonFrames->IsEmpty() || JsonFrames->Num()>100000)
        {
            Error = TEXT("Sequence needs 1 to 100000 explicit frame entries."); return false;
        }
        const FString Root = FPaths::GetPath(Working.SourceFilename);
        double PreviousTime = -DBL_MAX;
        for (const auto& Value : *JsonFrames)
        {
            if (IsImportCanceled(Feedback, Error)) return false;
            const TSharedPtr<FJsonObject>* ObjectPtr = nullptr;
            if (!Value.IsValid() || !Value->TryGetObject(ObjectPtr) || !ObjectPtr || !ObjectPtr->IsValid())
            {
                Error = TEXT("Each sequence frame must be an object."); return false;
            }
            const auto& Object = *ObjectPtr;
            FString Relative;
            if (!Object->TryGetStringField(TEXT("file"), Relative) && !Object->TryGetStringField(TEXT("path"), Relative))
            {
                if (!Object->TryGetStringField(TEXT("model"), Relative))
                {
                    const TSharedPtr<FJsonObject>* Model = nullptr;
                    if (Object->TryGetObjectField(TEXT("model"), Model) && Model && Model->IsValid())
                        (*Model)->TryGetStringField(TEXT("path"), Relative);
                }
            }
            double Time = 0;
            if (!Object->TryGetNumberField(TEXT("time_seconds"), Time) || !FMath::IsFinite(Time) || Time <= PreviousTime)
            {
                Error = TEXT("Frame time_seconds values must be finite and strictly increasing."); return false;
            }
            FString Status;
            if (Object->TryGetStringField(TEXT("status"), Status) && Status != TEXT("complete"))
            {
                Error = TEXT("The manifest contains an incomplete frame."); return false;
            }
            FString Path;
            if (!SafeRelativePath(Root, Relative, Path))
            {
                Error = TEXT("Frame path must stay inside the manifest directory."); return false;
            }
            if (Working.bStableIds && !FPaths::GetExtension(Path).Equals(TEXT("am53"), ESearchCase::IgnoreCase))
            {
                Error = TEXT("Stable-ID interpolation requires AM53 frames; PLY/splat sequences use independent sample-and-hold."); return false;
            }
            FAbuM53Frame Frame;
            if (bIndexOnly)
            {
                Frame.TimeSeconds=Time;
                Frame.ExternalFilename=Path;
                Working.Frames.Add(MoveTemp(Frame));
                PreviousTime=Time;
                continue;
            }
            if (!LoadFrame(Path, Time, Working.bStableIds, Frame, Error, RemainingBytes, Feedback)) return false;
            if (Working.bStableIds && !Working.Frames.IsEmpty() && !EqualIds(Working.Frames[0], Frame))
            {
                Error = TEXT("Stable-ID keyframes must have the same IDs and SH degree; split topology changes into clips."); return false;
            }
            Working.Frames.Add(MoveTemp(Frame));
            PreviousTime = Time;
        }
    }
    Working.bExternalStream=bIndexOnly;
    Working.ImportReport = bIndexOnly ? FString::Printf(TEXT("%d independent frame(s), external streaming index. Frame files must remain available under the selected source directory; they are NOT automatically cooked. Coordinate profile: %s."),Working.Frames.Num(),*Working.CoordinateProfile) : FString::Printf(TEXT("%d frame(s); %lld decoded bytes; FP32 SH0-3 and shape, rebased FP32 positions. Coordinate profile: %s. %s. Imported data is embedded for cooking; no external source is needed for playback. Import budget: %lld bytes."),
        Working.Frames.Num(), OriginalBudget-RemainingBytes, *Working.CoordinateProfile,
        Working.bStableIds ? TEXT("Stable-ID interpolation available") : TEXT("Independent frames: sample-and-hold"), OriginalBudget);
    if (IsImportCanceled(Feedback, Error)) return false;
    Result = MoveTemp(Working);
    return true;
}

bool AbuM53::DecodeFile(const FString& Filename,FAbuM53ImportResult& Result,FString& Error,int64 MaxDecodedBytes,
    const FAbuM53ImportFeedback* Feedback)
{
    return DecodeFileImpl(Filename,Result,Error,MaxDecodedBytes,false,Feedback);
}
bool AbuM53::ReadSequenceIndex(const FString& Filename,FAbuM53ImportResult& Result,FString& Error)
{
    return DecodeFileImpl(Filename,Result,Error,256,true,nullptr);
}
