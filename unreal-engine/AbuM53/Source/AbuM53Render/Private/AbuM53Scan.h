// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
#include "RenderGraphFwd.h"

// Exclusive uint32 sum, preserving input order. Arithmetic wraps modulo 2^32.
// Input must contain NumElements uint32 values; maximum 1,250,000 elements.
// A zero-element request returns a one-element zero buffer for RDG validity.
// The returned buffer is separate from Input and has no CPU readback dependency.
FRDGBufferRef AddAbuM53ExclusiveScan(FRDGBuilder& Graph, FRDGBufferRef Input, uint32 NumElements);
