// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53ActorFactory.h"
#include "AbuM53Actor.h"
#include "AbuM53Component.h"
#include "AssetRegistry/AssetData.h"

UAbuM53ActorFactory::UAbuM53ActorFactory()
{
    DisplayName=NSLOCTEXT("AbuM53","ActorFactory","Abu M53");
    NewActorClass=AAbuM53Actor::StaticClass();
    bUseSurfaceOrientation=false;
}
bool UAbuM53ActorFactory::CanCreateActorFrom(const FAssetData& AssetData,FText& OutErrorMsg)
{
    if (AssetData.IsInstanceOf(UAbuM53Asset::StaticClass())) return true;
    OutErrorMsg=NSLOCTEXT("AbuM53","ActorFactoryError","Select an imported Abu M53 asset.");
    return false;
}
void UAbuM53ActorFactory::PostSpawnActor(UObject* Asset,AActor* NewActor)
{
    Super::PostSpawnActor(Asset,NewActor);
    if (auto* Actor=Cast<AAbuM53Actor>(NewActor)) Actor->SplatComponent->SetAsset(Cast<UAbuM53Asset>(Asset));
}
UObject* UAbuM53ActorFactory::GetAssetFromActorInstance(AActor* ActorInstance)
{
    if (const auto* Actor=Cast<AAbuM53Actor>(ActorInstance)) return Actor->SplatComponent->Asset;
    return nullptr;
}
