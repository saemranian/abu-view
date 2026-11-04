// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
#include "RenderGraphFwd.h"

// Returns one uint: zero means the entire selected view was composited;
// one means no tile color was composited and the caller must draw its fallback.
// Projected: three float4s per splat (mean/radius, conic/alpha, linear color/depth).
// SortedKeys: uint2(depth key, projected index), ascending camera depth.
FRDGBufferRef AddAbuM53TilePass(
    FRDGBuilder& Graph, FRDGBufferRef Projected, FRDGBufferRef SortedKeys,
    uint32 Total, FRDGTextureRef Depth, FRDGTextureRef SceneColor,
    FIntRect Rect, float AlphaCutoff);
