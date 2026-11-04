// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Shaders.h"
#include "AbuM53Scan.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RenderingThread.h"
#include "RHIGPUReadback.h"

namespace
{
enum class ERadixPattern : uint8 { PermutedBuckets, EqualKeys, Descending };
struct FRadixCase
{
    uint32 Count;
    ERadixPattern Pattern;
};

// Distinct buckets are strictly increasing in unsigned 32-bit key order. Their
// low bits also differ, so validation exercises all eight radix passes.
uint32 BucketKey(uint32 Bucket)
{
    return Bucket == 1023 ? 0xffffffffu : (Bucket << 22) | ((Bucket * 977u) & 0x003fffffu);
}

uint32 InputKey(uint32 Index, uint32 Count, ERadixPattern Pattern)
{
    if (Pattern == ERadixPattern::EqualKeys) return 0x81234567u;
    if (Pattern == ERadixPattern::Descending) return Count - 1 - Index;
    return BucketKey(((Index & 1023u) * 405u + 173u) & 1023u);
}

bool RunRadixCases(FAutomationTestBase& Test, TArray<FRadixCase> Cases)
{
    if (GUsingNullRHI || !IsFeatureLevelSupported(GMaxRHIShaderPlatform, ERHIFeatureLevel::SM5))
    {
        Test.AddError(TEXT("Radix GPU validation requires an active SM5+ rendering device"));
        return false;
    }
    TArray<FString> Failures;
    uint64 Compared = 0;
    const int32 CaseCount = Cases.Num();
    ENQUEUE_RENDER_COMMAND(AbuM53RadixReadbackTest)(
        [Cases = MoveTemp(Cases), &Failures, &Compared](FRHICommandListImmediate& Cmd)
    {
        auto* ShaderMap = GetGlobalShaderMap(GMaxRHIFeatureLevel);
        for (const FRadixCase& Case : Cases)
        {
            const uint32 Count = Case.Count;
            // Stress uses about128MiB of CPU input plus GPU ping-pong/readback
            // buffers. The exact stable oracle needs no second O(N) allocation.
            TArray<FUintVector2> Input;
            Input.SetNumUninitialized(Count);
            for (uint32 i = 0; i < Count; ++i) Input[i] = FUintVector2(InputKey(i, Count, Case.Pattern), i);
            FRHIGPUBufferReadback Readback(TEXT("AbuM53.RadixTestReadback"));
            FRDGBuilder Graph(Cmd);
            auto KeyDesc = FRDGBufferDesc::CreateStructuredDesc(sizeof(FUintVector2), Count);
            KeyDesc.Usage |= EBufferUsageFlags::SourceCopy;
            FRDGBufferRef In = Graph.CreateBuffer(KeyDesc, TEXT("AbuM53.RadixTestKeysA"));
            Graph.QueueBufferUpload(In, Input.GetData(), uint64(Count) * sizeof(FUintVector2));
            FRDGBufferRef Out = Graph.CreateBuffer(KeyDesc, TEXT("AbuM53.RadixTestKeysB"));
            const uint32 Groups = FMath::DivideAndRoundUp(Count, 256u);
            const FIntVector Dispatch(FMath::Min(Groups, 65535u), FMath::DivideAndRoundUp(Groups, 65535u), 1);
            FRDGBufferRef Histogram = Graph.CreateBuffer(
                FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), Groups * 16), TEXT("AbuM53.RadixTestHistogram"));
            for (uint32 Shift = 0; Shift < 32; Shift += 4)
            {
                auto* H = Graph.AllocParameters<FAbuM53HistogramCS::FParameters>();
                H->TotalCount = Count;
                H->GroupCount = Groups;
                H->DigitShift = Shift;
                H->KeysIn = Graph.CreateSRV(In);
                H->Histogram = Graph.CreateUAV(Histogram);
                FComputeShaderUtils::AddPass(Graph, RDG_EVENT_NAME("AbuM53.TestRadixHistogram"),
                    TShaderMapRef<FAbuM53HistogramCS>(ShaderMap), H, Dispatch);

                FRDGBufferRef Offsets = AddAbuM53ExclusiveScan(Graph, Histogram, Groups * 16);
                auto* S = Graph.AllocParameters<FAbuM53ScatterCS::FParameters>();
                S->TotalCount = Count;
                S->GroupCount = Groups;
                S->DigitShift = Shift;
                S->KeysIn = Graph.CreateSRV(In);
                S->OffsetsIn = Graph.CreateSRV(Offsets);
                S->KeysOut = Graph.CreateUAV(Out);
                FComputeShaderUtils::AddPass(Graph, RDG_EVENT_NAME("AbuM53.TestRadixScatter"),
                    TShaderMapRef<FAbuM53ScatterCS>(ShaderMap), S, Dispatch);
                Swap(In, Out);
            }
            const uint32 Bytes = Count * sizeof(FUintVector2);
            AddEnqueueCopyPass(Graph, &Readback, In, Bytes);
            Graph.Execute();
            Cmd.SubmitAndBlockUntilGPUIdle();
            if (!Readback.IsReady())
            {
                Failures.Add(FString::Printf(TEXT("Radix readback not ready for %u points"), Count));
                continue;
            }
            const FUintVector2* Actual = static_cast<const FUintVector2*>(Readback.Lock(Bytes));
            if (!Actual)
            {
                Failures.Add(TEXT("Could not map radix test readback"));
                continue;
            }
            uint32 SortedIndex = 0;
            bool Matched = true;
            auto Compare = [&](uint32 ExpectedKey, uint32 ExpectedId)
            {
                const FUintVector2 Value = Actual[SortedIndex];
                if (Value.X != ExpectedKey || Value.Y != ExpectedId)
                {
                    Failures.Add(FString::Printf(
                        TEXT("Radix mismatch count=%u pattern=%u output=%u expected=(%u,%u) actual=(%u,%u)"),
                        Count, uint32(Case.Pattern), SortedIndex, ExpectedKey, ExpectedId, Value.X, Value.Y));
                    Matched = false;
                }
                else ++Compared;
                ++SortedIndex;
            };
            if (Case.Pattern == ERadixPattern::PermutedBuckets)
            {
                // 445 is the modular inverse of405 modulo1024. These IDs are
                // precisely the original increasing IDs in each sorted bucket.
                for (uint32 Bucket = 0; Bucket < 1024 && Matched; ++Bucket)
                {
                    const uint32 FirstId = (((Bucket + 1024u - 173u) & 1023u) * 445u) & 1023u;
                    for (uint32 Id = FirstId; Id < Count && Matched; Id += 1024)
                        Compare(BucketKey(Bucket), Id);
                }
            }
            else
            {
                for (uint32 i = 0; i < Count && Matched; ++i)
                {
                    const uint32 Id = Case.Pattern == ERadixPattern::EqualKeys ? i : Count - 1 - i;
                    Compare(InputKey(Id, Count, Case.Pattern), Id);
                }
            }
            if (Matched && SortedIndex != Count) Failures.Add(TEXT("Radix oracle did not cover the full result"));
            Readback.Unlock();
        }
    });
    FlushRenderingCommands();
    for (const FString& Failure : Failures) Test.AddError(Failure);
    Test.AddInfo(FString::Printf(TEXT("Compared %llu exact stable GPU key/index pairs across %d radix cases"), Compared, CaseCount));
    return Failures.IsEmpty();
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53RadixGPUValidation, "AbuM53.Render.RadixGPU",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter | EAutomationTestFlags::NonNullRHI)
bool FAbuM53RadixGPUValidation::RunTest(const FString& Parameters)
{
    TArray<FRadixCase> Cases;
    for (uint32 Count : {1u, 255u, 256u, 257u, 1000u, 65536u, 1000000u})
        Cases.Add({Count, ERadixPattern::PermutedBuckets});
    Cases.Add({1000000, ERadixPattern::EqualKeys});
    Cases.Add({65536, ERadixPattern::Descending});
    return RunRadixCases(*this, MoveTemp(Cases));
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53RadixGPUStress, "AbuM53.Stress.Radix2DDispatchBoundary",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::StressFilter | EAutomationTestFlags::NonNullRHI)
bool FAbuM53RadixGPUStress::RunTest(const FString& Parameters)
{
    // 65,535 complete groups plus one point forces the shader's second dispatch row.
    // Opt-in StressFilter keeps this large allocation out of ordinary engine tests.
    TArray<FRadixCase> Cases;
    Cases.Add({16776961, ERadixPattern::PermutedBuckets});
    return RunRadixCases(*this, MoveTemp(Cases));
}
#endif
