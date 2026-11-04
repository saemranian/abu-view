// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Tiles.h"
#include "CommonRenderResources.h"
#include "GlobalShader.h"
#include "HAL/IConsoleManager.h"
#include "PipelineStateCache.h"
#include "RHIStaticStates.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "ShaderParameterStruct.h"

namespace
{
constexpr uint32 TileEdge = 16;
constexpr uint32 MaximumCapacity = 1024;
constexpr uint64 HardMemoryBudget = 256ull * 1024 * 1024;
constexpr uint64 AllocationHeadroom = 16ull * 1024 * 1024;
static TAutoConsoleVariable<int32> CVarM53TileCapacity(
    TEXT("r.AbuM53.TileCapacity"), 1024,
    TEXT("Maximum splats per 16x16 tile, rounded down to a power of two (32..1024). Overflow uses the whole-view quad fallback."),
    ECVF_RenderThreadSafe);
static TAutoConsoleVariable<float> CVarM53TileTermination(
    TEXT("r.AbuM53.TileTransmittanceCutoff"), 0.0001f,
    TEXT("Tile transmittance early termination threshold. Zero disables termination; maximum 0.01."),
    ECVF_RenderThreadSafe);
}

class FAbuM53TileBinCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53TileBinCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53TileBinCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, TotalCount)
        SHADER_PARAMETER(uint32, BinGroupsX)
        SHADER_PARAMETER(uint32, TilesX)
        SHADER_PARAMETER(uint32, TilesY)
        SHADER_PARAMETER(uint32, TileCapacity)
        SHADER_PARAMETER(FUintVector2, ImageSize)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, TileProjected)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, GlobalSortedKeys)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, TileCounts)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, TileIndices)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, TileOverflow)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P)
    { return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5); }
};

class FAbuM53TileSortCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53TileSortCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53TileSortCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, TilesX)
        SHADER_PARAMETER(uint32, TileCapacity)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, TileCountsIn)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, TileOverflowIn)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, TileIndices)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P)
    { return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5); }
};

class FAbuM53TileCompositeCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53TileCompositeCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53TileCompositeCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, TilesX)
        SHADER_PARAMETER(uint32, TileCapacity)
        SHADER_PARAMETER(FUintVector2, ImageSize)
        SHADER_PARAMETER(FIntPoint, ViewOffset)
        SHADER_PARAMETER(float, TileAlphaCutoff)
        SHADER_PARAMETER(float, TransmittanceCutoff)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, TileCountsIn)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, TileOverflowIn)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, SortedTileIndices)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, GlobalSortedKeys)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, TileProjected)
        SHADER_PARAMETER_RDG_TEXTURE(Texture2D, OpaqueDepth)
        SHADER_PARAMETER_RDG_TEXTURE_UAV(RWTexture2D<float4>, TileColorOut)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P)
    { return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5); }
};

class FAbuM53TileResolveVS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53TileResolveVS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53TileResolveVS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P)
    { return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5); }
};

class FAbuM53TileResolvePS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53TileResolvePS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53TileResolvePS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(FIntPoint, ViewOffset)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, TileOverflowIn)
        SHADER_PARAMETER_RDG_TEXTURE(Texture2D<float4>, TileColorIn)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P)
    { return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5); }
};

IMPLEMENT_GLOBAL_SHADER(FAbuM53TileBinCS, "/Plugin/AbuM53/Private/AbuM53Tiles.usf", "TileBinCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FAbuM53TileSortCS, "/Plugin/AbuM53/Private/AbuM53Tiles.usf", "TileSortCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FAbuM53TileCompositeCS, "/Plugin/AbuM53/Private/AbuM53Tiles.usf", "TileCompositeCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FAbuM53TileResolveVS, "/Plugin/AbuM53/Private/AbuM53Tiles.usf", "TileResolveVS", SF_Vertex);
IMPLEMENT_GLOBAL_SHADER(FAbuM53TileResolvePS, "/Plugin/AbuM53/Private/AbuM53Tiles.usf", "TileResolvePS", SF_Pixel);

BEGIN_SHADER_PARAMETER_STRUCT(FAbuM53TileResolvePass, )
    SHADER_PARAMETER_STRUCT_INCLUDE(FAbuM53TileResolvePS::FParameters, PS)
    RENDER_TARGET_BINDING_SLOTS()
END_SHADER_PARAMETER_STRUCT()

FRDGBufferRef AddAbuM53TilePass(
    FRDGBuilder& Graph, FRDGBufferRef Projected, FRDGBufferRef SortedKeys,
    uint32 Total, FRDGTextureRef Depth, FRDGTextureRef SceneColor,
    FIntRect Rect, float AlphaCutoff)
{
    FRDGBufferRef Overflow = Graph.CreateBuffer(
        FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), 1), TEXT("AbuM53.TileOverflow"));

    // Reject unrepresentable/budget-exceeding work before allocating tile storage.
    // Hardware device-loss/OOM recovery belongs to UE; the budget gate avoids an
    // intentional over-allocation and returns a GPU-readable fallback flag.
    const int32 Width = Rect.Width(), Height = Rect.Height();
    if (!Projected || !SortedKeys || !Depth || !SceneColor || Total == 0 ||
        Width <= 0 || Height <= 0 || Width > 16384 || Height > 16384 ||
        Rect.Min.X < 0 || Rect.Min.Y < 0 ||
        Rect.Max.X > Depth->Desc.Extent.X || Rect.Max.Y > Depth->Desc.Extent.Y ||
        Rect.Max.X > SceneColor->Desc.Extent.X || Rect.Max.Y > SceneColor->Desc.Extent.Y)
    {
        AddClearUAVPass(Graph, Graph.CreateUAV(Overflow), 1u);
        return Overflow;
    }

    const uint32 TilesX = FMath::DivideAndRoundUp(uint32(Width), TileEdge);
    const uint32 TilesY = FMath::DivideAndRoundUp(uint32(Height), TileEdge);
    const uint64 TileCount = uint64(TilesX) * TilesY;
    const uint64 PixelBytes = uint64(Width) * Height * 16ull;
    uint32 Capacity = MaximumCapacity;
    const uint32 Requested = uint32(FMath::Clamp(CVarM53TileCapacity.GetValueOnRenderThread(), 32, int32(MaximumCapacity)));
    while (Capacity > Requested) Capacity >>= 1;
    while (Capacity >= 32 &&
           PixelBytes + TileCount * (sizeof(uint32) + uint64(Capacity) * sizeof(uint32)) + sizeof(uint32)
               > HardMemoryBudget - AllocationHeadroom)
    {
        Capacity >>= 1;
    }
    if (Capacity < 32)
    {
        AddClearUAVPass(Graph, Graph.CreateUAV(Overflow), 1u);
        return Overflow;
    }

    RDG_EVENT_SCOPE(Graph, "AbuM53.Tiles %ux%u capacity %u", TilesX, TilesY, Capacity);
    AddClearUAVPass(Graph, Graph.CreateUAV(Overflow), 0u);
    FRDGBufferRef Counts = Graph.CreateBuffer(
        FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), uint32(TileCount)), TEXT("AbuM53.TileCounts"));
    FRDGBufferRef Indices = Graph.CreateBuffer(
        FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), uint32(TileCount * Capacity)), TEXT("AbuM53.TileIndices"));
    AddClearUAVPass(Graph, Graph.CreateUAV(Counts), 0u);
    const auto ColorDesc = FRDGTextureDesc::Create2D(
        FIntPoint(Width, Height), PF_A32B32G32R32F, FClearValueBinding::Transparent,
        TexCreate_ShaderResource | TexCreate_UAV);
    FRDGTextureRef Color = Graph.CreateTexture(ColorDesc, TEXT("AbuM53.TileColor"));
    const FIntVector TileGroups(TilesX, TilesY, 1);
    auto* ShaderMap = GetGlobalShaderMap(GMaxRHIFeatureLevel);

    auto* Bin = Graph.AllocParameters<FAbuM53TileBinCS::FParameters>();
    Bin->TotalCount = Total;
    const uint32 BinGroupCount = FMath::DivideAndRoundUp(Total, 256u);
    Bin->BinGroupsX = FMath::Min(BinGroupCount, 65535u);
    Bin->TilesX = TilesX;
    Bin->TilesY = TilesY;
    Bin->TileCapacity = Capacity;
    Bin->ImageSize = FUintVector2(Width, Height);
    Bin->TileProjected = Graph.CreateSRV(Projected);
    Bin->GlobalSortedKeys = Graph.CreateSRV(SortedKeys);
    Bin->TileCounts = Graph.CreateUAV(Counts);
    Bin->TileIndices = Graph.CreateUAV(Indices);
    Bin->TileOverflow = Graph.CreateUAV(Overflow);
    FComputeShaderUtils::AddPass(Graph, RDG_EVENT_NAME("AbuM53.TileBin"),
        TShaderMapRef<FAbuM53TileBinCS>(ShaderMap), Bin,
        FIntVector(Bin->BinGroupsX, FMath::DivideAndRoundUp(BinGroupCount, Bin->BinGroupsX), 1));

    auto* Sort = Graph.AllocParameters<FAbuM53TileSortCS::FParameters>();
    Sort->TilesX = TilesX;
    Sort->TileCapacity = Capacity;
    Sort->TileCountsIn = Graph.CreateSRV(Counts);
    Sort->TileOverflowIn = Graph.CreateSRV(Overflow);
    Sort->TileIndices = Graph.CreateUAV(Indices);
    FComputeShaderUtils::AddPass(Graph, RDG_EVENT_NAME("AbuM53.TileSort"),
        TShaderMapRef<FAbuM53TileSortCS>(ShaderMap), Sort, TileGroups);

    auto* Composite = Graph.AllocParameters<FAbuM53TileCompositeCS::FParameters>();
    Composite->TilesX = TilesX;
    Composite->TileCapacity = Capacity;
    Composite->ImageSize = FUintVector2(Width, Height);
    Composite->ViewOffset = Rect.Min;
    Composite->TileAlphaCutoff = FMath::Clamp(AlphaCutoff, 0.0f, 0.999f);
    Composite->TransmittanceCutoff = FMath::Clamp(CVarM53TileTermination.GetValueOnRenderThread(), 0.0f, 0.01f);
    Composite->TileCountsIn = Graph.CreateSRV(Counts);
    Composite->TileOverflowIn = Graph.CreateSRV(Overflow);
    Composite->SortedTileIndices = Graph.CreateSRV(Indices);
    Composite->GlobalSortedKeys = Graph.CreateSRV(SortedKeys);
    Composite->TileProjected = Graph.CreateSRV(Projected);
    Composite->OpaqueDepth = Depth;
    Composite->TileColorOut = Graph.CreateUAV(Color);
    FComputeShaderUtils::AddPass(Graph, RDG_EVENT_NAME("AbuM53.TileComposite"),
        TShaderMapRef<FAbuM53TileCompositeCS>(ShaderMap), Composite, TileGroups);

    auto* Resolve = Graph.AllocParameters<FAbuM53TileResolvePass>();
    Resolve->PS.ViewOffset = Rect.Min;
    Resolve->PS.TileOverflowIn = Graph.CreateSRV(Overflow);
    Resolve->PS.TileColorIn = Color;
    Resolve->RenderTargets[0] = FRenderTargetBinding(SceneColor, ERenderTargetLoadAction::ELoad);
    const TShaderMapRef<FAbuM53TileResolveVS> VS(ShaderMap);
    const TShaderMapRef<FAbuM53TileResolvePS> PS(ShaderMap);
    Graph.AddPass(RDG_EVENT_NAME("AbuM53.TileResolve"), Resolve, ERDGPassFlags::Raster,
        [Resolve, VS, PS, Rect](FRHICommandList& Cmd)
        {
            Cmd.SetViewport(Rect.Min.X, Rect.Min.Y, 0, Rect.Max.X, Rect.Max.Y, 1);
            FGraphicsPipelineStateInitializer State;
            Cmd.ApplyCachedRenderTargets(State);
            State.BlendState = TStaticBlendState<CW_RGBA, BO_Add, BF_One, BF_InverseSourceAlpha,
                BO_Add, BF_One, BF_InverseSourceAlpha>::GetRHI();
            State.RasterizerState = TStaticRasterizerState<FM_Solid, CM_None>::GetRHI();
            State.DepthStencilState = TStaticDepthStencilState<false, CF_Always>::GetRHI();
            State.PrimitiveType = PT_TriangleList;
            State.BoundShaderState.VertexDeclarationRHI = GEmptyVertexDeclaration.VertexDeclarationRHI;
            State.BoundShaderState.VertexShaderRHI = VS.GetVertexShader();
            State.BoundShaderState.PixelShaderRHI = PS.GetPixelShader();
            SetGraphicsPipelineState(Cmd, State, 0);
            SetShaderParameters(Cmd, PS, PS.GetPixelShader(), Resolve->PS);
            Cmd.DrawPrimitive(0, 1, 1);
        });
    return Overflow;
}
