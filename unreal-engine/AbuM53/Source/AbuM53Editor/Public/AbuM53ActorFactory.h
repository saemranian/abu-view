// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
#include "ActorFactories/ActorFactory.h"
#include "AbuM53ActorFactory.generated.h"
UCLASS()
class ABUM53EDITOR_API UAbuM53ActorFactory : public UActorFactory
{
    GENERATED_BODY()
public:
    UAbuM53ActorFactory();
    virtual bool CanCreateActorFrom(const FAssetData& AssetData,FText& OutErrorMsg) override;
    virtual UObject* GetAssetFromActorInstance(AActor* ActorInstance) override;
protected:
    virtual void PostSpawnActor(UObject* Asset,AActor* NewActor) override;
};
