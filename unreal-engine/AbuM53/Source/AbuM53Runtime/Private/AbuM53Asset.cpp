// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Asset.h"

double UAbuM53Asset::GetDuration() const
{
    if (Frames.IsEmpty()) return 0;
    return FMath::Max(0.0, Frames.Last().TimeSeconds - Frames[0].TimeSeconds) + 1.0/FMath::Max(FramesPerSecond, 0.001);
}

int32 UAbuM53Asset::FindFrame(double Time) const
{
    if (Frames.IsEmpty()) return INDEX_NONE;
    if (!FMath::IsFinite(Time)) return 0;
    int32 Low=0, High=Frames.Num();
    while (Low<High)
    {
        const int32 Mid=Low+(High-Low)/2;
        if (Frames[Mid].TimeSeconds<=Time) Low=Mid+1; else High=Mid;
    }
    return FMath::Clamp(Low-1,0,Frames.Num()-1);
}

int64 UAbuM53Asset::GetDecodedBytes() const
{
    int64 Total=0;
    for (const auto& Frame : Frames) Total += Frame.PackedPoints.Num();
    return Total;
}

bool UAbuM53Asset::ImportFile(const FString& Filename, FString& Error)
{
    FAbuM53ImportResult Result;
    if (!AbuM53::DecodeFile(Filename,Result,Error)) return false;
    ReplaceData(MoveTemp(Result));
    return true;
}

void UAbuM53Asset::ReplaceData(FAbuM53ImportResult&& Result)
{
    check(IsInGameThread());
    Frames=MoveTemp(Result.Frames);
    SourceFilename=MoveTemp(Result.SourceFilename);
    CoordinateProfile=MoveTemp(Result.CoordinateProfile);
    ImportReport=MoveTemp(Result.ImportReport);
    FramesPerSecond=Result.FramesPerSecond;
    bStableIds=Result.bStableIds;
    bExternalStream=Result.bExternalStream;
    ++DataRevision;
    FrameCache.Empty();
}

TSharedPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe> UAbuM53Asset::GetFramePoints(int32 Index) const
{
    check(IsInGameThread());
    if (!Frames.IsValidIndex(Index)) return nullptr;
    if (const auto* Existing=FrameCache.Find(Index)) if (auto Strong=Existing->Pin()) return Strong;
    const auto& Frame=Frames[Index];
    if (Frame.SplatCount<0 || static_cast<int64>(Frame.SplatCount)*sizeof(FAbuM53GPUPoint)!=Frame.PackedPoints.Num()) return nullptr;
    auto Points=MakeShared<TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe>();
    Points->SetNumUninitialized(Frame.SplatCount);
    if (Frame.SplatCount) FMemory::Memcpy(Points->GetData(),Frame.PackedPoints.GetData(),Frame.PackedPoints.Num());
    TSharedPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe> ConstPoints=Points;
    FrameCache.Add(Index,ConstPoints);
    return ConstPoints;
}

void UAbuM53Asset::PostLoad()
{
    Super::PostLoad();
    ++DataRevision;
    FrameCache.Empty();
}
