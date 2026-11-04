// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53About.h"
#include "Misc/AutomationTest.h"
#include "Framework/Docking/TabManager.h"
#include "Widgets/Docking/SDockTab.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53AboutTest,"AbuM53.Editor.AboutTab",
    EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53AboutTest::RunTest(const FString& Parameters)
{
    const FString Document=AbuM53About::LoadDocument();
    TestTrue(TEXT("Packaged document has dependency attribution"),Document.Contains(TEXT("facebook/zstd")) && Document.Contains(TEXT("nianticlabs/spz")));
    TestTrue(TEXT("Original-code and separate engine terms available"),Document.Contains(TEXT("Apache-2.0")) && Document.Contains(TEXT("Engine Tools")));
    TestTrue(TEXT("Agent maintenance instructions available"),Document.Contains(TEXT("Antigravity")));
    const auto Tab=FGlobalTabmanager::Get()->TryInvokeTab(AbuM53About::TabName);
    TestTrue(TEXT("About tab registered and opens"),Tab.IsValid());
    if (Tab) { TestEqual(TEXT("About tab title"),Tab->GetTabLabel().ToString(),FString(TEXT("About Abu M53"))); Tab->RequestCloseTab(); }
    return true;
}
#endif
