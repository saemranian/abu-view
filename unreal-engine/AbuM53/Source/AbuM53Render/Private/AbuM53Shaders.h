// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GlobalShader.h"
#include "ShaderParameterStruct.h"
#include "SceneView.h"

class FAbuM53ProjectCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53ProjectCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53ProjectCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, PointCount)
        SHADER_PARAMETER(uint32, OutputOffset)
        SHADER_PARAMETER(FMatrix44f, LocalToClip)
        SHADER_PARAMETER(FMatrix44f, LocalToView)
        SHADER_PARAMETER(FVector3f, CameraLocal)
        SHADER_PARAMETER(FVector2f, ViewSize)
        SHADER_PARAMETER(float, Intensity)
        SHADER_PARAMETER(float, OpacityMultiplier)
        SHADER_PARAMETER(float, SplatScale)
        SHADER_PARAMETER(float, FilterVariance)
        SHADER_PARAMETER_STRUCT_REF(FViewUniformShaderParameters, View)
        SHADER_PARAMETER(uint32, CropEnabled)
        SHADER_PARAMETER(FVector3f, CropMin)
        SHADER_PARAMETER(FVector3f, CropMax)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, SourcePoints)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float4>, Projected)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint2>, KeysOut)
    END_SHADER_PARAMETER_STRUCT()
    static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& P) { return IsFeatureLevelSupported(P.Platform, ERHIFeatureLevel::SM5); }
};

class FAbuM53HistogramCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53HistogramCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53HistogramCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, TotalCount)
        SHADER_PARAMETER(uint32, GroupCount)
        SHADER_PARAMETER(uint32, DigitShift)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, KeysIn)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, Histogram)
    END_SHADER_PARAMETER_STRUCT()
};
class FAbuM53PrefixCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53PrefixCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53PrefixCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, GroupCount)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, HistogramIn)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, Offsets)
    END_SHADER_PARAMETER_STRUCT()
};
class FAbuM53ScatterCS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53ScatterCS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53ScatterCS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, TotalCount)
        SHADER_PARAMETER(uint32, GroupCount)
        SHADER_PARAMETER(uint32, DigitShift)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, KeysIn)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, OffsetsIn)
        SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint2>, KeysOut)
    END_SHADER_PARAMETER_STRUCT()
};
class FAbuM53DrawVS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53DrawVS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53DrawVS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(uint32, TotalCount)
        SHADER_PARAMETER(FVector2f, ViewSize)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, ProjectedIn)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint2>, SortedKeys)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, TileOverflow)
    END_SHADER_PARAMETER_STRUCT()
};
class FAbuM53DrawPS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53DrawPS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53DrawPS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER_RDG_TEXTURE(Texture2D, SceneDepth)
        SHADER_PARAMETER(float, AlphaCutoff)
    END_SHADER_PARAMETER_STRUCT()
};
class FAbuM53SoftwareVS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53SoftwareVS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53SoftwareVS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
    END_SHADER_PARAMETER_STRUCT()
};
class FAbuM53SoftwarePS : public FGlobalShader
{
    DECLARE_GLOBAL_SHADER(FAbuM53SoftwarePS);
    SHADER_USE_PARAMETER_STRUCT(FAbuM53SoftwarePS, FGlobalShader);
    BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
        SHADER_PARAMETER(FVector2f, ViewMin)
        SHADER_PARAMETER(FVector2f, ViewSize)
        SHADER_PARAMETER(FVector2f, SoftwareSize)
        SHADER_PARAMETER_STRUCT_REF(FViewUniformShaderParameters, View)
        SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, SoftwarePixels)
    END_SHADER_PARAMETER_STRUCT()
};
