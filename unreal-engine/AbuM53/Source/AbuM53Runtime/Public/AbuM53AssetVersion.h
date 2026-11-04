// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"

// The on-disk format version is independent of the plugin release number.
struct ABUM53RUNTIME_API FAbuM53AssetVersion
{
    static const FGuid GUID;
    enum Type
    {
        BeforeCustomVersion = 0,
        ContiguousFramePayload = 1,
        LatestVersion = ContiguousFramePayload
    };
};
