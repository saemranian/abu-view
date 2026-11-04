// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Component.h"
#include "Async/Async.h"
#include "Async/ParallelFor.h"
#include "Misc/Paths.h"

struct FAbuM53StreamFrame
{
    TSharedPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe> Points;
    FVector SourceOrigin=FVector::ZeroVector;
    int64 Bytes=0;
    int32 FrameIndex=INDEX_NONE;
    FString CoordinateProfile;
};

// Accessed only on the game thread. Captured ownership outlives an invalidated component.
// One decode may run per component; canceled work retains its slot until it finishes.
struct FAbuM53AsyncGate { bool bBusy=false; };

namespace { TArray<TWeakObjectPtr<UAbuM53Component>> RegisteredComponents; }

UAbuM53Component::UAbuM53Component()
{
    PrimaryComponentTick.bCanEverTick=true;
    bTickInEditor=true;
    AsyncGate=MakeShared<FAbuM53AsyncGate,ESPMode::ThreadSafe>();
}

const TArray<TWeakObjectPtr<UAbuM53Component>>& UAbuM53Component::GetRegisteredComponents() { return RegisteredComponents; }

void UAbuM53Component::OnRegister()
{
    Super::OnRegister();
    SynchronizeSourceState();
    RegisteredComponents.AddUnique(this);
}

void UAbuM53Component::OnUnregister()
{
    // Details edits temporarily unregister native components. Their decoded samples
    // and in-flight requests remain valid and must survive the following register.
    RegisteredComponents.Remove(this);
    Super::OnUnregister();
}

void UAbuM53Component::OnComponentDestroyed(bool bDestroyingHierarchy)
{
    CancelLoad();
    ResetRenderCache();
    Super::OnComponentDestroyed(bDestroyingHierarchy);
}

void UAbuM53Component::ResetRenderCache()
{
    CachedPoints.Reset();
    CachedAsset.Reset();
    CachedRevision=INDEX_NONE;
    CachedFrame=INDEX_NONE;
    CachedTime=TNumericLimits<double>::Lowest();
    bCachedInterpolation=false;
}

int64 UAbuM53Component::GetStreamingBudgetBytes() const
{
    return static_cast<int64>(FMath::Clamp(StreamingCacheMiB,16,8192))*1024*1024;
}

void UAbuM53Component::SynchronizeSourceState()
{
    const int32 Revision=Asset ? Asset->DataRevision : INDEX_NONE;
    if (ObservedAsset.Get()!=Asset || ObservedRevision!=Revision)
    {
        // Asset can also change through Details, undo, Blueprint assignment or reimport.
        // A frame index alone does not identify the source of an external sample.
        CancelLoad();
        ResetRenderCache();
        ObservedAsset=Asset;
        ObservedRevision=Revision;
    }
    if (ObservedCacheMiB!=StreamingCacheMiB)
    {
        ObservedCacheMiB=StreamingCacheMiB;
        StreamFailed.Empty();
        LastStreamingError.Reset();
        TrimStreamCache(GetStreamingBudgetBytes());
    }
}

void UAbuM53Component::TrimStreamCache(int64 BudgetBytes)
{
    auto CountBytes=[this]()
    {
        int64 Bytes=DisplayedStreamFrame ? DisplayedStreamFrame->Bytes : 0;
        for (const auto& Item : StreamCache)
            if (Item.Value!=DisplayedStreamFrame) Bytes+=Item.Value->Bytes;
        return Bytes;
    };
    StreamingResidentBytes=CountBytes();
    while (StreamingResidentBytes>BudgetBytes && !StreamCache.IsEmpty())
    {
        int32 Victim=INDEX_NONE;
        uint64 Oldest=MAX_uint64;
        for (const auto& Item : StreamCache)
        {
            if (Item.Value==DisplayedStreamFrame) continue;
            const uint64 LastUse=StreamLastUse.FindRef(Item.Key);
            if (LastUse<Oldest) { Victim=Item.Key; Oldest=LastUse; }
        }
        if (Victim==INDEX_NONE) break;
        StreamCache.Remove(Victim);
        StreamLastUse.Remove(Victim);
        StreamingResidentBytes=CountBytes();
    }
    // A user can reduce the budget below the displayed frame size. Drop its final
    // retained reference too, rather than hiding an over-budget fallback allocation.
    if (StreamingResidentBytes>BudgetBytes && DisplayedStreamFrame)
    {
        StreamCache.Remove(DisplayedStreamFrame->FrameIndex);
        StreamLastUse.Remove(DisplayedStreamFrame->FrameIndex);
        DisplayedStreamFrame.Reset();
        StreamingResidentBytes=CountBytes();
    }
}

void UAbuM53Component::SetAsset(UAbuM53Asset* InAsset)
{
    CancelLoad();
    Asset=InAsset;
    ObservedAsset=Asset;
    ObservedRevision=Asset ? Asset->DataRevision : INDEX_NONE;
    ResetRenderCache();
    if (Asset && !Asset->Frames.IsEmpty()) TimeSeconds=Asset->Frames[0].TimeSeconds;
}

void UAbuM53Component::Seek(double Seconds)
{
    if (!FMath::IsFinite(Seconds)) return;
    ++StreamSeekEpoch;
    TimeSeconds=Seconds;
    if (Asset && !Asset->Frames.IsEmpty()) TimeSeconds=FMath::Clamp(Seconds,Asset->Frames[0].TimeSeconds,Asset->Frames.Last().TimeSeconds);
}

int32 UAbuM53Component::GetCurrentFrameIndex() const { return Asset ? Asset->FindFrame(TimeSeconds) : INDEX_NONE; }
int32 UAbuM53Component::GetDisplayedFrameIndex() const
{
    if (!Asset || ObservedAsset.Get()!=Asset || ObservedRevision!=Asset->DataRevision) return INDEX_NONE;
    if (Asset->bExternalStream) return DisplayedStreamFrame ? DisplayedStreamFrame->FrameIndex : INDEX_NONE;
    return CachedPoints && CachedAsset.Get()==Asset && CachedRevision==Asset->DataRevision ? CachedFrame : INDEX_NONE;
}
int32 UAbuM53Component::GetDisplayedSplatCount() const
{
    if (GetDisplayedFrameIndex()==INDEX_NONE) return 0;
    return Asset->bExternalStream ? DisplayedStreamFrame->Points->Num() : CachedPoints->Num();
}
FVector UAbuM53Component::GetSourceOrigin() const
{
    if (Asset && Asset->bExternalStream) return DisplayedStreamFrame ? DisplayedStreamFrame->SourceOrigin : FVector::ZeroVector;
    const int32 Index=GetCurrentFrameIndex();
    return Asset && Asset->Frames.IsValidIndex(Index) ? Asset->Frames[Index].SourceOrigin : FVector::ZeroVector;
}

FMatrix UAbuM53Component::GetSourceAxisMatrix() const
{
    bool IsRUB=SourceAxes==EAbuM53SourceAxes::RightUpBack;
    if (SourceAxes==EAbuM53SourceAxes::Auto && Asset)
    {
        FString Profile=Asset->CoordinateProfile;
        if (Asset->bExternalStream && DisplayedStreamFrame && DisplayedStreamFrame->CoordinateProfile!=TEXT("unspecified")) Profile=DisplayedStreamFrame->CoordinateProfile;
        else if (Asset->Frames.IsValidIndex(GetCurrentFrameIndex()))
        {
            const FString& FrameProfile=Asset->Frames[GetCurrentFrameIndex()].SourceCoordinateProfile;
            if (FrameProfile!=TEXT("unspecified")) Profile=FrameProfile;
        }
        IsRUB=Profile==TEXT("right_up_back");
    }
    if (!IsRUB) return FMatrix::Identity;
    // Row-vector convention: source right/up/back -> UE forward/right/up = (-z,x,y).
    return FMatrix(FPlane(0,1,0,0),FPlane(0,0,1,0),FPlane(-1,0,0,0),FPlane(0,0,0,1));
}

TSharedPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe> UAbuM53Component::GetRenderPoints() const
{
    auto* Mutable=const_cast<UAbuM53Component*>(this);
    Mutable->SynchronizeSourceState();
    if (!Asset) return nullptr;
    if (Asset->bExternalStream)
    {
        Mutable->RequestStreamFrames();
        if (const auto* Frame=StreamCache.Find(GetCurrentFrameIndex()))
        {
            Mutable->DisplayedStreamFrame=*Frame;
            Mutable->StreamLastUse.Add(GetCurrentFrameIndex(),++Mutable->StreamUseCounter);
        }
        else ++Mutable->StreamingMisses;
        return DisplayedStreamFrame ? DisplayedStreamFrame->Points : nullptr;
    }
    const int32 Index=GetCurrentFrameIndex();
    const bool Interpolate=Asset->bStableIds && bInterpolateStableIds && Asset->Frames.IsValidIndex(Index+1);
    if (CachedPoints.IsValid() && CachedAsset.Get()==Asset && CachedFrame==Index && CachedRevision==Asset->DataRevision && bCachedInterpolation==Interpolate &&
        (!Interpolate || CachedTime==TimeSeconds)) return CachedPoints;
    CachedPoints=Asset->GetFramePoints(Index);
    CachedAsset=Asset;
    CachedRevision=Asset->DataRevision;
    CachedFrame=Index;
    CachedTime=TimeSeconds;
    bCachedInterpolation=Interpolate;
    if (!Interpolate || !CachedPoints) return CachedPoints;
    const auto Next=Asset->GetFramePoints(Index+1);
    if (!Next || Next->Num()!=CachedPoints->Num()) return CachedPoints;
    const auto& A=Asset->Frames[Index];
    const auto& B=Asset->Frames[Index+1];
    const float Alpha=FMath::Clamp(static_cast<float>((TimeSeconds-A.TimeSeconds)/(B.TimeSeconds-A.TimeSeconds)),0.f,1.f);
    if (Alpha<=0) return CachedPoints;
    auto Mixed=MakeShared<TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe>();
    Mixed->SetNumUninitialized(CachedPoints->Num());
    const FVector3f Offset=FVector3f(B.SourceOrigin-A.SourceOrigin);
    ParallelFor(Mixed->Num(),[&](int32 I)
    {
        const auto& P=(*CachedPoints)[I]; const auto& Q=(*Next)[I]; auto& R=(*Mixed)[I];
        R=P;
        R.PositionOpacity=FMath::Lerp(P.PositionOpacity,Q.PositionOpacity+FVector4f(Offset,0),Alpha);
        for (int Axis=0; Axis<3; ++Axis)
            R.ScaleDegree[Axis]=FMath::Exp(FMath::Lerp(FMath::Loge(FMath::Max(P.ScaleDegree[Axis],1e-20f)),FMath::Loge(FMath::Max(Q.ScaleDegree[Axis],1e-20f)),Alpha));
        const FQuat4f Rotation=FQuat4f::Slerp(FQuat4f(P.Rotation.X,P.Rotation.Y,P.Rotation.Z,P.Rotation.W),FQuat4f(Q.Rotation.X,Q.Rotation.Y,Q.Rotation.Z,Q.Rotation.W),Alpha).GetNormalized();
        R.Rotation=FVector4f(Rotation.X,Rotation.Y,Rotation.Z,Rotation.W);
        for (int J=0; J<12; ++J) R.SH[J]=FMath::Lerp(P.SH[J],Q.SH[J],Alpha);
    });
    CachedPoints=Mixed;
    return CachedPoints;
}

void UAbuM53Component::TickComponent(float DeltaTime,ELevelTick TickType,FActorComponentTickFunction* Function)
{
    Super::TickComponent(DeltaTime,TickType,Function);
    SynchronizeSourceState();
    if (bPlaying && Asset && Asset->Frames.Num()>=2 && FMath::IsFinite(PlayRate))
    {
        TimeSeconds += static_cast<double>(DeltaTime)*PlayRate;
        const double Start=Asset->Frames[0].TimeSeconds;
        const double Duration=Asset->GetDuration();
        if (bLoop && Duration>0)
        {
            double Wrapped=FMath::Fmod(TimeSeconds-Start,Duration);
            if (Wrapped<0) Wrapped+=Duration;
            TimeSeconds=Start+Wrapped;
        }
        else if (TimeSeconds<Start || TimeSeconds>Asset->Frames.Last().TimeSeconds)
        {
            TimeSeconds=FMath::Clamp(TimeSeconds,Start,Asset->Frames.Last().TimeSeconds);
            bPlaying=false;
        }
    }
    // Paused seeks and editor previews must make progress without a render callback.
    RequestStreamFrames();
}

void UAbuM53Component::CancelLoad()
{
    ++LoadGeneration;
    StreamCache.Empty();
    StreamLastUse.Empty();
    StreamPending.Empty();
    StreamFailed.Empty();
    DisplayedStreamFrame.Reset();
    StreamingResidentBytes=0;
    StreamingMisses=0;
    ++StreamSeekEpoch;
    StreamLastRequestFrame=INDEX_NONE;
    LastStreamingError.Reset();
    bLoadQueued=false;
    QueuedFilename.Reset();
    ObservedAsset=Asset;
    ObservedRevision=Asset ? Asset->DataRevision : INDEX_NONE;
}
bool UAbuM53Component::IsLoadPending() const { return bLoadQueued || AsyncGate->bBusy; }
void UAbuM53Component::LoadFileAsync(const FString& Filename)
{
    CancelLoad();
    const FString Extension=FPaths::GetExtension(Filename).ToLower();
    QueuedGeneration=LoadGeneration;
    QueuedFilename=Filename;
    bQueuedStreaming=bStreamExternalSequences && (Extension==TEXT("am53seq") || Extension==TEXT("json"));
    bLoadQueued=true;
    StartQueuedLoad();
}

void UAbuM53Component::StartQueuedLoad()
{
    check(IsInGameThread());
    if (!bLoadQueued || AsyncGate->bBusy) return;
    const uint64 Generation=QueuedGeneration;
    const FString Filename=MoveTemp(QueuedFilename);
    const bool Stream=bQueuedStreaming;
    bLoadQueued=false;
    AsyncGate->bBusy=true;
    const auto Gate=AsyncGate;
    const TWeakObjectPtr<UAbuM53Component> WeakThis(this);
    Async(EAsyncExecution::ThreadPool,[WeakThis,Gate,Generation,Filename,Stream]()
    {
        auto Result=MakeShared<FAbuM53ImportResult,ESPMode::ThreadSafe>();
        FString Error;
        const bool Success=Stream ? AbuM53::ReadSequenceIndex(Filename,*Result,Error) : AbuM53::DecodeFile(Filename,*Result,Error);
        AsyncTask(ENamedThreads::GameThread,[WeakThis,Gate,Generation,Result,Success,Error]() mutable
        {
            Gate->bBusy=false;
            auto* Component=WeakThis.Get();
            if (!Component) return;
            if (Component->bLoadQueued) { Component->StartQueuedLoad(); return; }
            if (Component->LoadGeneration!=Generation) return;
            if (Success)
            {
                auto* NewAsset=NewObject<UAbuM53Asset>(Component);
                NewAsset->ReplaceData(MoveTemp(*Result));
                Component->SetAsset(NewAsset);
            }
            Component->OnLoadCompleted.Broadcast(Success,Success ? TEXT("Abu M53 import complete") : Error);
        });
    });
}

void UAbuM53Component::RequestStreamFrames()
{
    if (!Asset || !Asset->bExternalStream) return;
    const int32 Current=GetCurrentFrameIndex();
    if (const auto* Ready=StreamCache.Find(Current))
    {
        DisplayedStreamFrame=*Ready;
        StreamLastUse.Add(Current,++StreamUseCounter);
    }
    if (!bPlaying && StreamLastRequestFrame!=INDEX_NONE && StreamLastRequestFrame!=Current) ++StreamSeekEpoch;
    StreamLastRequestFrame=Current;
    RequestStreamFrame(Current);
    const int32 Next=Current+(PlayRate<0 ? -1 : 1);
    if (Asset->Frames.IsValidIndex(Next)) RequestStreamFrame(Next);
    else if (bLoop) RequestStreamFrame(PlayRate<0 ? Asset->Frames.Num()-1 : 0);
}

void UAbuM53Component::RequestStreamFrame(int32 Index)
{
    if (!Asset || !Asset->Frames.IsValidIndex(Index) || StreamCache.Contains(Index) ||
        StreamPending.Contains(Index) || StreamFailed.Contains(Index) || !StreamPending.IsEmpty() || bLoadQueued || AsyncGate->bBusy) return;
    const uint64 Generation=LoadGeneration;
    const uint64 SeekEpoch=StreamSeekEpoch;
    const TWeakObjectPtr<UAbuM53Component> WeakThis(this);
    const TWeakObjectPtr<UAbuM53Asset> StreamAsset=Asset;
    const int32 SourceRevision=Asset->DataRevision;
    const FString Filename=Asset->Frames[Index].ExternalFilename;
    // Reserve decoded-cache room for current, next and the last ready seek fallback.
    const int64 FrameBudget=GetStreamingBudgetBytes()/3;
    // Reserve one incoming sample before dispatch. Retain other decoded frames by
    // recency, so a short clip that fits the budget loops without reading it again.
    TrimStreamCache(GetStreamingBudgetBytes()-FrameBudget);
    StreamPending.Add(Index);
    AsyncGate->bBusy=true;
    const auto Gate=AsyncGate;
    Async(EAsyncExecution::ThreadPool,[WeakThis,StreamAsset,SourceRevision,Gate,Generation,SeekEpoch,Index,Filename,FrameBudget]()
    {
        FAbuM53ImportResult Data;
        FString Error;
        const bool Success=AbuM53::DecodeFile(Filename,Data,Error,FrameBudget);
        auto Decoded=MakeShared<FAbuM53StreamFrame,ESPMode::ThreadSafe>();
        if (Success && Data.Frames.Num()==1)
        {
            auto& Frame=Data.Frames[0];
            auto Points=MakeShared<TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe>();
            Points->SetNumUninitialized(Frame.SplatCount);
            FMemory::Memcpy(Points->GetData(),Frame.PackedPoints.GetData(),Frame.PackedPoints.Num());
            Decoded->Points=Points;
            Decoded->SourceOrigin=Frame.SourceOrigin;
            Decoded->Bytes=Frame.PackedPoints.Num();
            Decoded->FrameIndex=Index;
            Decoded->CoordinateProfile=Frame.SourceCoordinateProfile;
        }
        AsyncTask(ENamedThreads::GameThread,[WeakThis,StreamAsset,SourceRevision,Gate,Generation,SeekEpoch,Index,Decoded,Success,Error,FrameBudget]()
        {
            Gate->bBusy=false;
            auto* Component=WeakThis.Get();
            if (!Component) return;
            if (Component->bLoadQueued) { Component->StartQueuedLoad(); return; }
            if (Component->LoadGeneration!=Generation || Component->Asset!=StreamAsset.Get()) return;
            Component->StreamPending.Remove(Index);
            if (!Component->Asset || Component->Asset->DataRevision!=SourceRevision || Component->Asset->Frames.IsEmpty()) return;
            if (Component->StreamSeekEpoch!=SeekEpoch) return;
            if (!Success || !Decoded->Points)
            {
                // A larger budget entered during a decode must permit a fresh retry.
                if (FrameBudget!=Component->GetStreamingBudgetBytes()/3) return;
                Component->LastStreamingError=Error.IsEmpty() ? TEXT("Stream frame did not produce a static cloud.") : Error;
                if (Error.Contains(TEXT("budget")))
                    Component->LastStreamingError+=TEXT(" Increase Streaming Cache MiB to at least three decoded frames (3072 MiB for 3-million-splat frames).");
                Component->StreamFailed.Add(Index);
                return;
            }
            const int32 Current=Component->GetCurrentFrameIndex();
            const int32 Count=Component->Asset->Frames.Num();
            const int32 Next=(Current+(Component->PlayRate<0 ? Count-1 : 1))%Count;
            if (Decoded->Bytes>Component->GetStreamingBudgetBytes()/3)
            {
                Component->LastStreamingError=TEXT("Decoded frame exceeds one third of Streaming Cache MiB. Increase the cache budget.");
                Component->StreamFailed.Add(Index);
                return;
            }
            Component->LastStreamingError.Reset();
            Component->StreamCache.Add(Index,Decoded);
            Component->StreamLastUse.Add(Index,++Component->StreamUseCounter);
            if (Index!=Current && Index!=Next)
            {
                // Slow I/O during continuous playback still shows the latest ready sample.
                // A seek epoch change above rejects old requests instead of displaying them.
                const bool InPlaybackDirection=Component->PlayRate>=0 ? Index<Current : Index>Current;
                if (Component->bPlaying && InPlaybackDirection) Component->DisplayedStreamFrame=Decoded;
                Component->TrimStreamCache(Component->GetStreamingBudgetBytes());
                return;
            }
            if (Index==Current) Component->DisplayedStreamFrame=Decoded;
            Component->TrimStreamCache(Component->GetStreamingBudgetBytes());
        });
    });
}
