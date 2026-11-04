// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53SourceCache.h"
#include "Misc/AutomationTest.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RenderingThread.h"
#include "RHIGPUReadback.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53SourceCacheGPUValidation,"AbuM53.Render.SourceCacheGPU",
    EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter|EAutomationTestFlags::NonNullRHI)
bool FAbuM53SourceCacheGPUValidation::RunTest(const FString& Parameters)
{
    if (GUsingNullRHI)
    {
        AddError(TEXT("SourceCacheGPU requires an active rendering device"));
        return false;
    }
    TArray<FString> Failures;
    uint64 ComparedBytes=0;
    ENQUEUE_RENDER_COMMAND(AbuM53SourceCacheValidation)([&Failures,&ComparedBytes](FRHICommandListImmediate& Cmd)
    {
        using FPoints=TSharedPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe>;
        auto MakePoints=[](int32 Marker)->FPoints
        {
            auto Points=MakeShared<TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe>();
            Points->SetNum(8);
            for (int32 I=0; I<Points->Num(); ++I)
            {
                (*Points)[I].PositionOpacity=FVector4f(float(Marker),float(I),-3.f,0.75f);
                (*Points)[I].SH[11]=FVector4f(1.f,2.f,3.f,float(Marker+I));
            }
            return Points;
        };
        auto Check=[&](bool Condition,const TCHAR* Message) { if (!Condition) Failures.Add(Message); };
        auto CheckReadback=[&](FRHIGPUBufferReadback& Readback,const TArray<FAbuM53GPUPoint>& Expected)
        {
            const uint32 Bytes=Expected.Num()*sizeof(FAbuM53GPUPoint);
            Cmd.SubmitAndBlockUntilGPUIdle();
            if (!Readback.IsReady()) { Failures.Add(TEXT("GPU source readback not ready")); return; }
            const void* Actual=Readback.Lock(Bytes);
            if (!Actual) { Failures.Add(TEXT("GPU source readback cannot be mapped")); return; }
            Check(FMemory::Memcmp(Actual,Expected.GetData(),Bytes)==0,TEXT("GPU source cache changed sample bytes"));
            ComparedBytes+=Bytes;
            Readback.Unlock();
        };
        FPoints Samples[3]={MakePoints(100),MakePoints(200),MakePoints(300)};
        constexpr uint64 Page=64*1024;
        FAbuM53SourceCache Cache;
        for (int32 I=0; I<6; ++I)
        {
            Cache.BeginFrame(I+1,3*Page);
            FRHIGPUBufferReadback Readback(TEXT("AbuM53.SourceCacheReadback"));
            FRDGBuilder Graph(Cmd);
            const auto Source=Cache.Acquire(Graph,53,Samples[I%3]);
            Check(Source==Cache.Acquire(Graph,53,Samples[I%3]),TEXT("two views in the same graph share one source"));
            AddEnqueueCopyPass(Graph,&Readback,Source,Samples[I%3]->Num()*sizeof(FAbuM53GPUPoint));
            Graph.Execute();
            CheckReadback(Readback,*Samples[I%3]);
            const auto Stats=Cache.GetStats();
            Check(Stats.ResidentBytes+Stats.ReservedBytes<=3*Page,TEXT("warm cache stays within its aligned budget"));
        }
        auto Stats=Cache.GetStats();
        Check(Stats.UploadCount==3,TEXT("three sample loop uploads only its three warm-up samples"));
        Check(Stats.CacheHits>=3 && Stats.PendingReuses==3,TEXT("completed and pending source hits are counted separately"));
        Check(Stats.UploadBytes==uint64(3*8*sizeof(FAbuM53GPUPoint)),TEXT("upload telemetry counts payload bytes"));
        Check(Stats.Entries==3 && Stats.ReservedBytes==0,TEXT("three completed GPU samples remain resident"));

        Cache.BeginFrame(7,Page);
        Stats=Cache.GetStats();
        Check(Stats.Entries==1 && Stats.ResidentBytes<=Page,TEXT("budget shrink evicts least recent completed sources"));
        {
            FRHIGPUBufferReadback Readback(TEXT("AbuM53.SourceEvictionReadback"));
            FRDGBuilder Graph(Cmd);
            auto Source=Cache.Acquire(Graph,53,Samples[0]);
            AddEnqueueCopyPass(Graph,&Readback,Source,Samples[0]->Num()*sizeof(FAbuM53GPUPoint));
            Graph.Execute();
            CheckReadback(Readback,*Samples[0]);
        }
        Check(Cache.GetStats().UploadCount==4,TEXT("an evicted sample is uploaded again correctly"));

        Cache.BeginFrame(8,0);
        {
            FRHIGPUBufferReadback Readback(TEXT("AbuM53.SourceDisabledReadback"));
            FRDGBuilder Graph(Cmd);
            auto Source=Cache.Acquire(Graph,53,Samples[0]);
            AddEnqueueCopyPass(Graph,&Readback,Source,Samples[0]->Num()*sizeof(FAbuM53GPUPoint));
            Graph.Execute();
            CheckReadback(Readback,*Samples[0]);
        }
        Stats=Cache.GetStats();
        Check(Stats.Entries==0 && Stats.ResidentBytes==0 && Stats.ReservedBytes==0,TEXT("disabled retention still draws but retains no source"));
        Check(Stats.UncachedUploads==1,TEXT("disabled upload is reported as uncached"));

        // Two uploads before execution with only one cache slot. Pending output
        // pointers cannot be evicted or overwritten to make room for the second.
        FAbuM53SourceCache PendingCache;
        PendingCache.BeginFrame(1,Page);
        {
            FRHIGPUBufferReadback First(TEXT("AbuM53.PendingFirstReadback")),Second(TEXT("AbuM53.PendingSecondReadback"));
            FRDGBuilder Graph(Cmd);
            auto A=PendingCache.Acquire(Graph,53,Samples[0]);
            auto B=PendingCache.Acquire(Graph,53,Samples[1]);
            AddEnqueueCopyPass(Graph,&First,A,Samples[0]->Num()*sizeof(FAbuM53GPUPoint));
            AddEnqueueCopyPass(Graph,&Second,B,Samples[1]->Num()*sizeof(FAbuM53GPUPoint));
            Stats=PendingCache.GetStats();
            Check(Stats.Entries==1 && Stats.ReservedBytes==Page && Stats.UncachedUploads==1,TEXT("pending cache pressure uses an uncached fallback"));
            PendingCache.BeginFrame(2,0);
            Check(PendingCache.GetStats().Entries==1,TEXT("in-flight extraction remains protected during budget shrink"));
            Graph.Execute();
            CheckReadback(First,*Samples[0]);
            CheckReadback(Second,*Samples[1]);
        }
        Check(PendingCache.GetStats().Entries==0,TEXT("pending budget shrink is applied after extraction"));

        // Destroy both the owning cache and caller's CPU allocation before graph
        // execution: graph captures must keep NoCopy and extraction addresses alive.
        {
            FRHIGPUBufferReadback Readback(TEXT("AbuM53.SourceLifetimeReadback"));
            FRDGBuilder Graph(Cmd);
            auto Temporary=MakePoints(900);
            TArray<FAbuM53GPUPoint> Expected=*Temporary;
            TWeakPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe> Weak=Temporary;
            {
                FAbuM53SourceCache ShortLivedCache;
                ShortLivedCache.BeginFrame(1,Page);
                auto Source=ShortLivedCache.Acquire(Graph,99,Temporary);
                AddEnqueueCopyPass(Graph,&Readback,Source,Temporary->Num()*sizeof(FAbuM53GPUPoint));
                Temporary.Reset();
            }
            Check(Weak.IsValid(),TEXT("NoCopy allocation survives its caller until graph execution"));
            Graph.Execute();
            CheckReadback(Readback,Expected);
            Check(!Weak.IsValid(),TEXT("GPU cache does not retain CPU samples after upload"));
        }
    });
    FlushRenderingCommands();
    for (const FString& Failure : Failures) AddError(Failure);
    AddInfo(FString::Printf(TEXT("Compared %llu exact GPU source bytes through warm reuse, LRU eviction, disabled cache, pending budget shrink and shutdown lifetime."),ComparedBytes));
    return Failures.IsEmpty();
}
#endif
