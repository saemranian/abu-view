// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53SourceCache.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"

namespace
{
struct FSourceKey
{
    uint32 ComponentId=0;
    const void* Allocation=nullptr;
    bool operator==(const FSourceKey& Other) const { return ComponentId==Other.ComponentId && Allocation==Other.Allocation; }
    friend uint32 GetTypeHash(const FSourceKey& Key) { return HashCombine(::GetTypeHash(Key.ComponentId),PointerHash(Key.Allocation)); }
};
struct FSourceEntry
{
    TWeakPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe> Points;
    TRefCountPtr<FRDGPooledBuffer> Buffer;
    FRDGBuilder* PendingGraph=nullptr;
    FRDGBufferRef PendingSource=nullptr;
    uint64 ReservedBytes=0;
    uint64 LastUse=0;
    uint64 LastFrame=0;
};
uint64 ReserveBytes(uint64 Bytes)
{
    // UE uses page-aligned pooled buffers, with power-of-two alignment available
    // on other allocation paths. Reserve conservatively and reconcile on extraction.
    uint64 Rounded=64*1024;
    while (Rounded<Bytes) Rounded*=2;
    return Rounded;
}
}

struct FAbuM53SourceCache::FState
{
    TMap<FSourceKey,TSharedPtr<FSourceEntry>> Entries;
    FAbuM53SourceCacheStats Counters;
    uint64 Budget=0;
    uint64 Frame=0;
    uint64 UseCounter=0;

    uint64 RetainedBytes() const
    {
        uint64 Bytes=0;
        for (const auto& Pair : Entries)
            Bytes+=Pair.Value->PendingGraph ? Pair.Value->ReservedBytes :
                (Pair.Value->Buffer ? Pair.Value->Buffer->GetAlignedSize() : 0);
        return Bytes;
    }
    void Trim(uint64 TargetBytes)
    {
        while (RetainedBytes()>TargetBytes)
        {
            TOptional<FSourceKey> Victim;
            uint64 Oldest=MAX_uint64;
            for (const auto& Pair : Entries)
            {
                // QueueBufferExtraction owns a pointer into this entry. Pending
                // uploads also remain counted until execution has completed.
                if (!Pair.Value->PendingGraph && Pair.Value->LastUse<Oldest)
                {
                    Oldest=Pair.Value->LastUse;
                    Victim=Pair.Key;
                }
            }
            if (!Victim) break;
            Entries.Remove(Victim.GetValue());
            ++Counters.Evictions;
        }
    }
};

FAbuM53SourceCache::FAbuM53SourceCache() : State(MakeShared<FState>()) {}

void FAbuM53SourceCache::BeginFrame(uint64 Frame,uint64 BudgetBytes)
{
    State->Frame=Frame;
    State->Budget=BudgetBytes;
    for (auto It=State->Entries.CreateIterator(); It; ++It)
    {
        const auto& Entry=It.Value();
        if (!Entry->PendingGraph && (!Entry->Points.IsValid() || Frame-Entry->LastFrame>120))
        {
            It.RemoveCurrent();
            ++State->Counters.Evictions;
        }
    }
    State->Trim(BudgetBytes);
}

FRDGBufferRef FAbuM53SourceCache::Acquire(FRDGBuilder& Graph,uint32 ComponentId,
    const TSharedPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe>& Points)
{
    check(Points && !Points->IsEmpty());
    const FSourceKey Key{ComponentId,Points.Get()};
    if (const auto* Existing=State->Entries.Find(Key))
    {
        const auto& Entry=*Existing;
        // A recycled CPU address must not match an expired allocation identity.
        if (Entry->Points.Pin()==Points)
        {
            Entry->LastUse=++State->UseCounter;
            Entry->LastFrame=State->Frame;
            if (Entry->PendingGraph==&Graph)
            {
                ++State->Counters.PendingReuses;
                return Entry->PendingSource;
            }
            if (!Entry->PendingGraph && Entry->Buffer)
            {
                ++State->Counters.CacheHits;
                return Graph.RegisterExternalBuffer(Entry->Buffer);
            }
        }
        if (!Entry->PendingGraph)
        {
            State->Entries.Remove(Key);
            ++State->Counters.Evictions;
        }
    }

    const uint64 Bytes=uint64(Points->Num())*sizeof(FAbuM53GPUPoint);
    const uint64 Reserved=ReserveBytes(Bytes);
    ++State->Counters.UploadCount;
    State->Counters.UploadBytes+=Bytes;
    const bool MayAdmit=Reserved<=State->Budget && !State->Entries.Contains(Key);
    if (MayAdmit) State->Trim(State->Budget-Reserved);
    const bool Admit=MayAdmit && State->RetainedBytes()<=State->Budget-Reserved;
    auto Desc=FRDGBufferDesc::CreateStructuredDesc(16,Points->Num()*16);
    Desc.Usage|=EBufferUsageFlags::SourceCopy;
    auto* Source=Graph.CreateBuffer(Desc,TEXT("AbuM53.Source"));
    Graph.QueueBufferUpload(Source,Points->GetData(),Bytes,ERDGInitialDataFlags::NoCopy);
    if (!Admit)
    {
        ++State->Counters.UncachedUploads;
        // No extraction: the graph owns this oversized or pressure fallback.
        // Keep the NoCopy pointer alive even if the component is edited/destroyed.
        Graph.AddPostExecuteCallback([KeepPoints=Points]() {});
        return Source;
    }

    auto Entry=MakeShared<FSourceEntry>();
    Entry->Points=Points;
    Entry->PendingGraph=&Graph;
    Entry->PendingSource=Source;
    Entry->ReservedBytes=Reserved;
    Entry->LastUse=++State->UseCounter;
    Entry->LastFrame=State->Frame;
    State->Entries.Add(Key,Entry);
    Graph.QueueBufferExtraction(Source,&Entry->Buffer);
    // Heap-stable entry and shared cache state outlive the extension if it shuts
    // down with this graph queued. UE fills extraction outputs before callbacks.
    Graph.AddPostExecuteCallback([KeepState=State,Entry,KeepPoints=Points]()
    {
        Entry->PendingGraph=nullptr;
        Entry->PendingSource=nullptr;
        Entry->ReservedBytes=0;
        // GetAlignedSize accounts for actual pool padding. Also apply a budget
        // reduction that arrived while this extraction was protected.
        KeepState->Trim(KeepState->Budget);
    });
    return Source;
}

FAbuM53SourceCacheStats FAbuM53SourceCache::GetStats() const
{
    auto Result=State->Counters;
    Result.Entries=State->Entries.Num();
    for (const auto& Pair : State->Entries)
    {
        if (Pair.Value->PendingGraph) Result.ReservedBytes+=Pair.Value->ReservedBytes;
        else if (Pair.Value->Buffer) Result.ResidentBytes+=Pair.Value->Buffer->GetAlignedSize();
    }
    return Result;
}
