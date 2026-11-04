// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Scan.h"
#include "GlobalShader.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "ShaderParameterStruct.h"

class FAbuM53ScanBlocksCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53ScanBlocksCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53ScanBlocksCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, ScanCount)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, ScanInput)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, ScanOutput)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, ScanBlockTotals)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P)
    { return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5); }
};

class FAbuM53ScanAddCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53ScanAddCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53ScanAddCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, ScanCount)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, ScanBlockOffsets)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, ScanOutput)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P)
    { return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5); }
};

IMPLEMENT_GLOBAL_SHADER(FAbuM53ScanBlocksCS, "/Plugin/AbuM53/Private/AbuM53Scan.usf", "ScanBlocksCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FAbuM53ScanAddCS, "/Plugin/AbuM53/Private/AbuM53Scan.usf", "ScanAddCS", SF_Compute);

FRDGBufferRef AddAbuM53ExclusiveScan(FRDGBuilder& Graph, FRDGBufferRef Input, uint32 NumElements)
{
    constexpr uint32 ElementsPerBlock = 512;
    constexpr uint32 MaximumElements = 1250000; // 16 bins * ceil(20M splats / 256).
    checkf(NumElements <= MaximumElements, TEXT("Abu M53 histogram scan exceeds supported limit"));
    checkf(NumElements == 0 || (Input && Input->Desc.BytesPerElement == sizeof(uint32) && Input->Desc.NumElements >= NumElements),
        TEXT("Abu M53 scan needs a sufficiently large uint32 input buffer"));
    auto OutputDesc = FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), FMath::Max(1u, NumElements));
    OutputDesc.Usage |= EBufferUsageFlags::SourceCopy;
    FRDGBufferRef Output = Graph.CreateBuffer(OutputDesc, TEXT("AbuM53.ScanOffsets"));
    if (NumElements == 0)
    {
        AddClearUAVPass(Graph, Graph.CreateUAV(Output), 0u);
        return Output;
    }
    RDG_EVENT_SCOPE(Graph, "AbuM53.Scan %u", NumElements);
    const uint32 BlockCount = FMath::DivideAndRoundUp(NumElements, ElementsPerBlock);
    FRDGBufferRef Totals = Graph.CreateBuffer(
        FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), BlockCount), TEXT("AbuM53.ScanBlockTotals"));
    auto* ShaderMap = GetGlobalShaderMap(GMaxRHIFeatureLevel);
    auto* Blocks = Graph.AllocParameters<FAbuM53ScanBlocksCS::FParameters>();
    Blocks->ScanCount = NumElements;
    Blocks->ScanInput = Graph.CreateSRV(Input);
    Blocks->ScanOutput = Graph.CreateUAV(Output);
    Blocks->ScanBlockTotals = Graph.CreateUAV(Totals);
    FComputeShaderUtils::AddPass(Graph, RDG_EVENT_NAME("AbuM53.ScanBlocks"),
        TShaderMapRef<FAbuM53ScanBlocksCS>(ShaderMap), Blocks, FIntVector(BlockCount, 1, 1));
    if (BlockCount > 1)
    {
        FRDGBufferRef BlockOffsets = AddAbuM53ExclusiveScan(Graph, Totals, BlockCount);
        auto* Add = Graph.AllocParameters<FAbuM53ScanAddCS::FParameters>();
        Add->ScanCount = NumElements;
        Add->ScanBlockOffsets = Graph.CreateSRV(BlockOffsets);
        Add->ScanOutput = Graph.CreateUAV(Output);
        FComputeShaderUtils::AddPass(Graph, RDG_EVENT_NAME("AbuM53.ScanAddBases"),
            TShaderMapRef<FAbuM53ScanAddCS>(ShaderMap), Add,
            FIntVector(FMath::DivideAndRoundUp(NumElements, 256u), 1, 1));
    }
    return Output;
}

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "RenderingThread.h"
#include "RHIGPUReadback.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53ExclusiveScanTest, "AbuM53.Render.ExclusiveScanGPU",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter | EAutomationTestFlags::NonNullRHI)
bool FAbuM53ExclusiveScanTest::RunTest(const FString& Parameters)
{
    if (GUsingNullRHI || !IsFeatureLevelSupported(GMaxRHIShaderPlatform, ERHIFeatureLevel::SM5))
    {
        AddError(TEXT("ExclusiveScanGPU requires an active SM5+ rendering device"));
        return false;
    }
    TArray<FString> Failures;
    uint32 ComparedElements = 0;
    ENQUEUE_RENDER_COMMAND(AbuM53ScanReadbackTest)([&Failures, &ComparedElements](FRHICommandListImmediate& Cmd)
    {
        const uint32 Lengths[] = {0, 1, 2, 255, 256, 511, 512, 513, 1023, 1024, 1025, 62512, 312512, 1250000};
        for (uint32 Pattern = 0; Pattern < 4; ++Pattern)
        for (uint32 Count : Lengths)
        {
            TArray<uint32> Input;
            Input.SetNumUninitialized(FMath::Max(1u, Count));
            uint32 State = 0x53ab1234u;
            for (uint32 i = 0; i < uint32(Input.Num()); ++i)
            {
                State = State * 1664525u + 1013904223u;
                Input[i] = Pattern == 0 ? 0u : Pattern == 1 ? 1u : Pattern == 2 ? (State >> 24) : 0xffffffffu;
            }
            FRHIGPUBufferReadback Readback(TEXT("AbuM53.ScanTestReadback"));
            FRDGBuilder Graph(Cmd);
            FRDGBufferRef Source = CreateStructuredBuffer(Graph, TEXT("AbuM53.ScanTestInput"), Input);
            FRDGBufferRef Scanned = AddAbuM53ExclusiveScan(Graph, Source, Count);
            const uint32 Bytes = FMath::Max(1u, Count) * sizeof(uint32);
            AddEnqueueCopyPass(Graph, &Readback, Scanned, Bytes);
            Graph.Execute();
            // This explicit synchronization exists only in the automation test.
            Cmd.SubmitAndBlockUntilGPUIdle();
            if (!Readback.IsReady())
            {
                Failures.Add(FString::Printf(TEXT("Readback not ready: count=%u pattern=%u"), Count, Pattern));
                continue;
            }
            const uint32* Actual = static_cast<const uint32*>(Readback.Lock(Bytes));
            if (!Actual)
            {
                Failures.Add(TEXT("Could not map scan readback"));
                continue;
            }
            uint32 Expected = 0;
            for (uint32 i = 0; i < FMath::Max(1u, Count); ++i)
            {
                if (Actual[i] != Expected)
                {
                    Failures.Add(FString::Printf(TEXT("Scan mismatch count=%u pattern=%u index=%u expected=%u actual=%u"),
                        Count, Pattern, i, Expected, Actual[i]));
                    break;
                }
                Expected += Input[i];
                ++ComparedElements;
            }
            Readback.Unlock();
        }
    });
    FlushRenderingCommands();
    for (const FString& Failure : Failures) AddError(Failure);
    AddInfo(FString::Printf(TEXT("Compared %u GPU scan outputs across 56 size/pattern cases"), ComparedElements));
    return Failures.IsEmpty();
}
#endif
