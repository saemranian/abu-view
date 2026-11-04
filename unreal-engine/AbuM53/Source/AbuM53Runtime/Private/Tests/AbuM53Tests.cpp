// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Asset.h"
#include "AbuM53Component.h"
#include "Misc/AutomationTest.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"
#include "Interfaces/IPluginManager.h"
#include "UObject/StrongObjectPtr.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53SequenceSelectionTest,"AbuM53.Runtime.SequenceSelection",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53SequenceSelectionTest::RunTest(const FString& Parameters)
{
    UAbuM53Asset* Asset=NewObject<UAbuM53Asset>();
    TestEqual(TEXT("empty asset has no frame"),Asset->FindFrame(0),INDEX_NONE);
    Asset->Frames.SetNum(3);
    Asset->Frames[0].TimeSeconds=2;
    Asset->Frames[1].TimeSeconds=2.25;
    Asset->Frames[2].TimeSeconds=3;
    TestEqual(TEXT("before first holds first"),Asset->FindFrame(-10),0);
    TestEqual(TEXT("between irregular samples holds previous"),Asset->FindFrame(2.5),1);
    TestEqual(TEXT("exact boundary selects next"),Asset->FindFrame(3),2);
    TestEqual(TEXT("after last holds last"),Asset->FindFrame(100),2);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53FrameValidationTest,"AbuM53.Runtime.FrameValidation",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53FrameValidationTest::RunTest(const FString& Parameters)
{
    UAbuM53Asset* Asset=NewObject<UAbuM53Asset>();
    Asset->Frames.SetNum(1);
    Asset->Frames[0].SplatCount=2;
    Asset->Frames[0].PackedPoints.SetNumZeroed(256);
    TestFalse(TEXT("malformed serialized count is rejected"),Asset->GetFramePoints(0).IsValid());
    Asset->Frames[0].SplatCount=1;
    TestTrue(TEXT("valid packed frame is returned"),Asset->GetFramePoints(0).IsValid());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53InterpolationTest,"AbuM53.Runtime.StableIdInterpolation",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53InterpolationTest::RunTest(const FString& Parameters)
{
    UAbuM53Asset* Asset=NewObject<UAbuM53Asset>();
    Asset->Frames.SetNum(2);
    Asset->bStableIds=true;
    for (int32 I=0; I<2; ++I)
    {
        auto& Frame=Asset->Frames[I];
        Frame.TimeSeconds=I;
        Frame.SourceOrigin=FVector(I*10,0,0);
        Frame.SplatCount=1;
        FAbuM53GPUPoint Point;
        Point.ScaleDegree=FVector4f(I ? 4.f : 1.f,1,1,0);
        Frame.PackedPoints.SetNumUninitialized(sizeof(Point));
        FMemory::Memcpy(Frame.PackedPoints.GetData(),&Point,sizeof(Point));
    }
    UAbuM53Component* Component=NewObject<UAbuM53Component>();
    Component->SetAsset(Asset);
    Component->Seek(0.5);
    auto Points=Component->GetRenderPoints();
    TestTrue(TEXT("tracked frame resolves"),Points.IsValid());
    if (Points)
    {
        TestEqual(TEXT("different chunk origins interpolate in common space"),(*Points)[0].PositionOpacity.X,5.f);
        TestEqual(TEXT("scale interpolates logarithmically"),(*Points)[0].ScaleDegree.X,2.f);
    }
    Component->bInterpolateStableIds=false;
    Points=Component->GetRenderPoints();
    if (Points) TestEqual(TEXT("disabling interpolation invalidates cached mixture"),(*Points)[0].PositionOpacity.X,0.f);
    Asset->bStableIds=false;
    Component->bInterpolateStableIds=true;
    Points=Component->GetRenderPoints();
    if (Points) TestEqual(TEXT("independent frames never interpolate by array index"),(*Points)[0].PositionOpacity.X,0.f);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53ManifestIndexTest,"AbuM53.Runtime.ManifestIndexSafety",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53ManifestIndexTest::RunTest(const FString& Parameters)
{
    const FString Directory=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("AbuM53Tests"));
    IFileManager::Get().MakeDirectory(*Directory,true);
    const FString Path=FPaths::Combine(Directory,TEXT("index_test.am53seq"));
    const FString Valid=TEXT("{\"schema\":1,\"sequence_type\":\"independent_3dgs_frames\",\"fps\":30,\"frames\":[{\"time_seconds\":0,\"file\":\"a.ply\"},{\"time_seconds\":0.1,\"file\":\"b.ply\"}]}");
    TestTrue(TEXT("test fixture written"),FFileHelper::SaveStringToFile(Valid,*Path));
    FAbuM53ImportResult Result;
    FString Error;
    TestTrue(TEXT("streaming index loads without decoding frame files"),AbuM53::ReadSequenceIndex(Path,Result,Error));
    TestTrue(TEXT("external source contract explicit"),Result.bExternalStream);
    TestEqual(TEXT("all timestamps indexed"),Result.Frames.Num(),2);
    if (Result.Frames.Num()==2) TestEqual(TEXT("index does not allocate point payload"),Result.Frames[0].PackedPoints.Num(),0);
    const FString Traversal=Valid.Replace(TEXT("a.ply"),TEXT("../a.ply"));
    FFileHelper::SaveStringToFile(Traversal,*Path);
    TestFalse(TEXT("manifest parent traversal rejected"),AbuM53::ReadSequenceIndex(Path,Result,Error));
    IFileManager::Get().Delete(*Path);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53SPZImportTest,"AbuM53.Runtime.SPZVersionsAndMetadata",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53SPZImportTest::RunTest(const FString& Parameters)
{
    const auto Plugin=IPluginManager::Get().FindPlugin(TEXT("AbuM53"));
    if (!TestTrue(TEXT("plugin descriptor available"),Plugin.IsValid())) return false;
    const FString Fixtures=FPaths::Combine(Plugin->GetBaseDir(),TEXT("Tests/portable/fixtures"));
    for (int32 Version=1; Version<=4; ++Version)
    {
        for (int32 Degree : {0,3})
        {
            FAbuM53ImportResult Result;
            FString Error;
            const FString File=FPaths::Combine(Fixtures,FString::Printf(TEXT("spz_v%d_sh%d.spz"),Version,Degree));
            const bool Loaded=AbuM53::DecodeFile(File,Result,Error);
            TestTrue(*FString::Printf(TEXT("SPZ v%d SH%d loads: %s"),Version,Degree,*Error),Loaded);
            if (Loaded)
            {
                TestEqual(TEXT("SPZ single frame"),Result.Frames.Num(),1);
                TestEqual(TEXT("SPZ SH degree preserved"),Result.Frames[0].SHDegree,Degree);
                TestTrue(TEXT("SPZ antialias flag preserved"),Result.Frames[0].bSourceAntialiased);
                TestEqual(TEXT("SPZ coordinate profile preserved"),Result.CoordinateProfile,FString(TEXT("right_up_back")));
            }
        }
    }
    UAbuM53Component* Component=NewObject<UAbuM53Component>();
    Component->SourceAxes=EAbuM53SourceAxes::RightUpBack;
    const auto Position=Component->GetSourceAxisMatrix().TransformPosition(FVector(1,2,3));
    TestEqual(TEXT("RUB to UE forward"),Position.X,-3.0);
    TestEqual(TEXT("RUB to UE right"),Position.Y,1.0);
    TestEqual(TEXT("RUB to UE up"),Position.Z,2.0);
    return true;
}

struct FAbuM53LatestLoadState
{
    TStrongObjectPtr<UAbuM53Component> Component;
    FAutomationTestBase* Test=nullptr;
    double Deadline=0;
};
DEFINE_LATENT_AUTOMATION_COMMAND_ONE_PARAMETER(FAbuM53WaitForLatestLoad,TSharedPtr<FAbuM53LatestLoadState>,State);
bool FAbuM53WaitForLatestLoad::Update()
{
    if (State->Component->IsLoadPending())
    {
        if (FPlatformTime::Seconds()<State->Deadline) return false;
        State->Test->AddError(TEXT("Latest-request async import did not finish in time."));
        State->Component->CancelLoad();
        return true;
    }
    auto* Asset=State->Component->Asset.Get();
    State->Test->TestTrue(TEXT("latest queued valid import produces an asset"),Asset!=nullptr);
    if (Asset)
    {
        State->Test->TestEqual(TEXT("stale canceled requests cannot replace final asset"),FPaths::GetCleanFilename(Asset->SourceFilename),FString(TEXT("shell_binary.ply")));
        State->Test->TestEqual(TEXT("latest asset count is complete"),Asset->GetSplatCount(),1000);
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53LatestRequestTest,"AbuM53.Runtime.LatestAsyncRequestWins",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53LatestRequestTest::RunTest(const FString& Parameters)
{
    const auto Plugin=IPluginManager::Get().FindPlugin(TEXT("AbuM53"));
    if (!Plugin) return false;
    auto State=MakeShared<FAbuM53LatestLoadState>();
    State->Component.Reset(NewObject<UAbuM53Component>());
    State->Test=this;
    State->Deadline=FPlatformTime::Seconds()+20;
    const FString Fixtures=FPaths::Combine(Plugin->GetBaseDir(),TEXT("Tests/Fixtures"));
    State->Component->LoadFileAsync(FPaths::Combine(Fixtures,TEXT("not_present.ply")));
    State->Component->LoadFileAsync(FPaths::Combine(Fixtures,TEXT("shell.splat")));
    State->Component->CancelLoad();
    State->Component->LoadFileAsync(FPaths::Combine(Fixtures,TEXT("shell_0000.ply")));
    State->Component->LoadFileAsync(FPaths::Combine(Fixtures,TEXT("shell_binary.ply")));
    ADD_LATENT_AUTOMATION_COMMAND(FAbuM53WaitForLatestLoad(State));
    return true;
}
#endif
