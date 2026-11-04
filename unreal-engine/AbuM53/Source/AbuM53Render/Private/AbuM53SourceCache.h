// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AbuM53Types.h"
#include "RenderGraphFwd.h"

struct FAbuM53SourceCacheStats
{
    uint64 UploadCount=0;
    uint64 UploadBytes=0;
    uint64 CacheHits=0;
    uint64 PendingReuses=0;
    uint64 Evictions=0;
    uint64 UncachedUploads=0;
    uint64 ResidentBytes=0;
    uint64 ReservedBytes=0;
    int32 Entries=0;
};

// Render-thread-only immutable source buffers. CPU point ownership is weak except
// while a graph consumes an upload; this does not extend the component's CPU cache.
class FAbuM53SourceCache
{
public:
    FAbuM53SourceCache();
    void BeginFrame(uint64 Frame,uint64 BudgetBytes);
    FRDGBufferRef Acquire(FRDGBuilder& Graph,uint32 ComponentId,
        const TSharedPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe>& Points);
    FAbuM53SourceCacheStats GetStats() const;

private:
    struct FState;
    TSharedPtr<FState> State;
};
