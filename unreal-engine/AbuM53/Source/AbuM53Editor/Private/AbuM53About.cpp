// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53About.h"
#include "Framework/Docking/TabManager.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/EngineVersion.h"
#include "HAL/PlatformProcess.h"
#include "Styling/CoreStyle.h"
#include "ToolMenus.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Text/STextBlock.h"

namespace AbuM53About
{
const FName TabName(TEXT("AbuM53.About"));
namespace
{
FDelegateHandle MenuStartupHandle;
FString PluginFile(const TCHAR* Relative)
{
    const auto Plugin=IPluginManager::Get().FindPlugin(TEXT("AbuM53"));
    return Plugin ? FPaths::ConvertRelativePathToFull(FPaths::Combine(Plugin->GetBaseDir(),Relative)) : FString();
}
FReply OpenFile(const TCHAR* Relative)
{
    const FString Path=PluginFile(Relative);
    if (FPaths::FileExists(Path)) FPlatformProcess::LaunchFileInDefaultExternalApplication(*Path);
    return FReply::Handled();
}
TSharedRef<SDockTab> Spawn(const FSpawnTabArgs& Args)
{
    const auto Plugin=IPluginManager::Get().FindPlugin(TEXT("AbuM53"));
    const FString Version=Plugin ? Plugin->GetDescriptor().VersionName : TEXT("unavailable");
    auto Body=SNew(SVerticalBox);
    FString Document=LoadDocument();
    TArray<FString> Paragraphs;
    Document.ReplaceInline(TEXT("\r"),TEXT(""));
    Document.ReplaceInline(TEXT("<!-- provenance-review:start -->"),TEXT(""));
    Document.ReplaceInline(TEXT("<!-- provenance-review:end -->"),TEXT(""));
    Document.ParseIntoArray(Paragraphs,TEXT("\n\n"),true);
    for (FString Paragraph : Paragraphs)
    {
        // A deliberately small text presentation, not an HTML/Markdown executor.
        // The packaged Markdown remains the authoritative, independently editable document.
        if (Paragraph.StartsWith(TEXT("<!--"))) continue;
        const bool Heading=Paragraph.StartsWith(TEXT("#"));
        if (Heading) { while (Paragraph.StartsWith(TEXT("#"))) Paragraph.RightChopInline(1); Paragraph.TrimStartInline(); }
        Paragraph.ReplaceInline(TEXT("**"),TEXT(""));
        Paragraph.ReplaceInline(TEXT("`"),TEXT(""));
        Body->AddSlot().AutoHeight().Padding(0,0,0,10)
        [SNew(STextBlock).Text(FText::FromString(Paragraph)).AutoWrapText(true)
            .Font(FCoreStyle::GetDefaultFontStyle(Heading ? "Bold" : "Regular",Heading ? 14 : 11))];
    }
    UE_LOG(LogTemp,Display,TEXT("Abu M53 About: %s; loaded provenance document: %s"),*Version,*DocumentPath());
    return SNew(SDockTab).TabRole(ETabRole::NomadTab)
    [SNew(SBox).MinDesiredWidth(680).MinDesiredHeight(500)
        [SNew(SVerticalBox)
            +SVerticalBox::Slot().AutoHeight().Padding(16,12)
            [SNew(STextBlock).Text(FText::FromString(FString::Printf(TEXT("Abu M53  %s   |   Unreal Engine %s"),*Version,*FEngineVersion::Current().ToString())))
                .Font(FCoreStyle::GetDefaultFontStyle("Bold",18))]
            +SVerticalBox::Slot().AutoHeight().Padding(16,0,16,10)
            [SNew(STextBlock).Text(NSLOCTEXT("AbuM53","AboutIntro","Code origins, repositories, licenses and contribution history. Loaded from this installed plugin's documentation.")).AutoWrapText(true)]
            +SVerticalBox::Slot().AutoHeight().Padding(16,0,16,12)
            [SNew(SHorizontalBox)
                +SHorizontalBox::Slot().AutoWidth().Padding(0,0,8,0)
                [SNew(SButton).Text(NSLOCTEXT("AbuM53","OpenOrigins","Open full Markdown document")).OnClicked_Lambda([] { return OpenFile(TEXT("Docs/Legal/Repository_Origins_and_Licensing.md")); })]
                +SHorizontalBox::Slot().AutoWidth().Padding(0,0,8,0)
                [SNew(SButton).Text(NSLOCTEXT("AbuM53","OpenLicense","Open LICENSE")).OnClicked_Lambda([] { return OpenFile(TEXT("LICENSE")); })]
                +SHorizontalBox::Slot().AutoWidth()
                [SNew(SButton).Text(NSLOCTEXT("AbuM53","OpenNotices","Open third-party notices")).OnClicked_Lambda([] { return OpenFile(TEXT("THIRD_PARTY_NOTICES.md")); })]]
            +SVerticalBox::Slot().FillHeight(1).Padding(16,0,16,12)
            [SNew(SScrollBox)+SScrollBox::Slot()[Body]]]];
}
void Open() { FGlobalTabmanager::Get()->TryInvokeTab(TabName); }
void RegisterMenus()
{
    FToolMenuOwnerScoped Owner(TabName);
    auto& Section=UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.MainMenu.Window"))->FindOrAddSection(TEXT("AbuM53"));
    Section.AddMenuEntry(TEXT("AbuM53About"),NSLOCTEXT("AbuM53","AboutMenu","About Abu M53"),
        NSLOCTEXT("AbuM53","AboutTooltip","View Abu M53's version, code origins, repository inventory and licenses."),
        FSlateIcon(),FUIAction(FExecuteAction::CreateStatic(&Open)));
}
}
FString DocumentPath() { return PluginFile(TEXT("Docs/Legal/Repository_Origins_and_Licensing.md")); }
FString LoadDocument()
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text,*DocumentPath()))
        return TEXT("# Provenance document unavailable\n\nRestore Docs/Legal/Repository_Origins_and_Licensing.md from the matching Abu M53 release package.");
    return Text;
}
void Register()
{
    FGlobalTabmanager::Get()->RegisterNomadTabSpawner(TabName,FOnSpawnTab::CreateStatic(&Spawn))
        .SetDisplayName(NSLOCTEXT("AbuM53","AboutTab","About Abu M53")).SetMenuType(ETabSpawnerMenuType::Hidden);
    MenuStartupHandle=UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateStatic(&RegisterMenus));
}
void Unregister()
{
    UToolMenus::UnRegisterStartupCallback(MenuStartupHandle);
    MenuStartupHandle.Reset();
    UToolMenus::UnregisterOwner(TabName);
    if (const auto Tab=FGlobalTabmanager::Get()->FindExistingLiveTab(TabName)) Tab->RequestCloseTab();
    FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(TabName);
}
}
