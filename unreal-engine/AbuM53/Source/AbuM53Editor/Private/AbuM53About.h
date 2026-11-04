// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
namespace AbuM53About
{
    extern const FName TabName;
    FString DocumentPath();
    FString LoadDocument();
    void Register();
    void Unregister();
}
