// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Types.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/AutomationTest.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53ImportCancelTest,
    "AbuM53.Runtime.ImportCancellationPreservesResult",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FAbuM53ImportCancelTest::RunTest(const FString& Parameters)
{
    FAbuM53ImportResult Existing;
    Existing.SourceFilename = TEXT("Existing asset stays intact");
    Existing.Frames.SetNum(1);
    Existing.Frames[0].SplatCount = 123;
    FAbuM53ImportFeedback Feedback;
    Feedback.ShouldCancel = []() { return true; };
    FString Error;
    TestFalse(TEXT("canceled before any source access"), AbuM53::DecodeFile(TEXT("missing.ply"), Existing, Error, 1024 * 1024, &Feedback));
    TestEqual(TEXT("cancellation is reported"), Error, FString(TEXT("Import canceled.")));
    TestEqual(TEXT("old result survives early cancellation"), Existing.Frames[0].SplatCount, 123);

    const auto Plugin = IPluginManager::Get().FindPlugin(TEXT("AbuM53"));
    if (!TestTrue(TEXT("plugin fixture directory available"), Plugin.IsValid())) return false;
    const FString Fixture = FPaths::Combine(Plugin->GetBaseDir(), TEXT("Tests/Fixtures/shell_binary.ply"));
    bool bCanceled = false;
    int32 StageCount = 0;
    Feedback.ShouldCancel = [&bCanceled]() { return bCanceled; };
    Feedback.ReportProgress = [&bCanceled, &StageCount](const FString& Stage)
    {
        ++StageCount;
        if (Stage.StartsWith(TEXT("Packing "))) bCanceled = true;
    };
    TestFalse(TEXT("cancellation between decoding and packing is honored"), AbuM53::DecodeFile(Fixture, Existing, Error, 16 * 1024 * 1024, &Feedback));
    TestTrue(TEXT("the reader reached bounded conversion stages"), StageCount >= 3);
    TestTrue(TEXT("packing stage requested cancellation"), bCanceled);
    TestEqual(TEXT("old result survives mid-import cancellation"), Existing.Frames[0].SplatCount, 123);
    TestEqual(TEXT("old source survives mid-import cancellation"), Existing.SourceFilename, FString(TEXT("Existing asset stays intact")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53ExternalSequenceImportTest,
    "AbuM53.Runtime.ExternalSequenceImport",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)
bool FAbuM53ExternalSequenceImportTest::RunTest(const FString& Parameters)
{
    const auto Plugin = IPluginManager::Get().FindPlugin(TEXT("AbuM53"));
    if (!TestTrue(TEXT("plugin fixture directory available"), Plugin.IsValid())) return false;
    const FString Directory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("AbuM53Tests"));
    IFileManager::Get().MakeDirectory(*Directory, true);
    const FString FramePath = FPaths::Combine(Directory, TEXT("external_import_fixture.splat"));
    const FString ManifestPath = FPaths::Combine(Directory, TEXT("external_import_fixture.am53seq"));
    const FString Source = FPaths::Combine(Plugin->GetBaseDir(), TEXT("Tests/Fixtures/shell.splat"));
    if (!TestEqual(TEXT("test frame copied"), IFileManager::Get().Copy(*FramePath, *Source), static_cast<uint32>(COPY_OK))) return false;
    const FString Manifest = TEXT("{\"schema\":1,\"storage\":\"external\",\"sequence_type\":\"independent_3dgs_frames\",\"fps\":30,\"frames\":[{\"time_seconds\":0,\"file\":\"external_import_fixture.splat\"}]}");
    TestTrue(TEXT("external manifest written"), FFileHelper::SaveStringToFile(Manifest, *ManifestPath));
    FAbuM53ImportResult Result;
    FString Error;
    TestTrue(TEXT("normal import honors external storage without decoding frames"), AbuM53::DecodeFile(ManifestPath, Result, Error, 256));
    TestTrue(TEXT("asset declares external source dependency"), Result.bExternalStream);
    if (TestEqual(TEXT("all external samples indexed"), Result.Frames.Num(), 1))
    {
        TestEqual(TEXT("external index allocates no payload"), Result.Frames[0].PackedPoints.Num(), 0);
        TestTrue(TEXT("resolved external path retained"), FPaths::IsSamePath(Result.Frames[0].ExternalFilename, FramePath));
    }
    const FString Embedded = Manifest.Replace(TEXT("\"storage\":\"external\","), TEXT(""));
    FFileHelper::SaveStringToFile(Embedded, *ManifestPath);
    TestTrue(TEXT("absent storage preserves embedded import"), AbuM53::DecodeFile(ManifestPath, Result, Error, 512 * 1024));
    TestFalse(TEXT("default asset is self-contained"), Result.bExternalStream);
    if (Result.Frames.Num() == 1) TestTrue(TEXT("embedded default contains point data"), Result.Frames[0].PackedPoints.Num() > 0);
    FFileHelper::SaveStringToFile(Manifest.Replace(TEXT("external\""), TEXT("unknown\"")), *ManifestPath);
    TestFalse(TEXT("unknown storage mode rejected"), AbuM53::DecodeFile(ManifestPath, Result, Error));
    TestFalse(TEXT("failed import preserves previous result"), Result.bExternalStream);
    IFileManager::Get().Delete(*ManifestPath);
    IFileManager::Get().Delete(*FramePath);
    return true;
}
#endif
