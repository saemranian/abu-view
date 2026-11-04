// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AbuM53Actor.generated.h"
class UAbuM53Component;
UCLASS(BlueprintType, Blueprintable, meta=(DisplayName="Abu M53"))
class ABUM53RUNTIME_API AAbuM53Actor : public AActor
{
    GENERATED_BODY()
public:
    AAbuM53Actor();
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Abu M53") TObjectPtr<UAbuM53Component> SplatComponent;
};
