// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "Modules/ModuleManager.h"
#include "AssetToolsModule.h"
#include "AssetTypeActions_Base.h"
#include "AbuM53Asset.h"
#include "Toolkits/SimpleAssetEditor.h"
#include "AbuM53About.h"

class FAbuM53AssetActions : public FAssetTypeActions_Base
{
public:
    virtual FText GetName() const override { return NSLOCTEXT("AbuM53","AssetName","Abu M53 Gaussian Scene"); }
    virtual FColor GetTypeColor() const override { return FColor(25,185,205); }
    virtual UClass* GetSupportedClass() const override { return UAbuM53Asset::StaticClass(); }
    virtual uint32 GetCategories() override { return EAssetTypeCategories::Misc; }
    virtual void OpenAssetEditor(const TArray<UObject*>& Objects,TSharedPtr<IToolkitHost> Host) override
    {
        FSimpleAssetEditor::CreateEditor(Host.IsValid() ? EToolkitMode::WorldCentric : EToolkitMode::Standalone,Host,Objects);
    }
};

class FAbuM53EditorModule : public IModuleInterface
{
    TSharedPtr<IAssetTypeActions> Actions;
public:
    virtual void StartupModule() override
    {
        AbuM53About::Register();
        Actions=MakeShared<FAbuM53AssetActions>();
        FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get().RegisterAssetTypeActions(Actions.ToSharedRef());
    }
    virtual void ShutdownModule() override
    {
        AbuM53About::Unregister();
        if (Actions.IsValid() && FModuleManager::Get().IsModuleLoaded(TEXT("AssetTools")))
            FModuleManager::GetModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get().UnregisterAssetTypeActions(Actions.ToSharedRef());
        Actions.Reset();
    }
};
IMPLEMENT_MODULE(FAbuM53EditorModule,AbuM53Editor)
