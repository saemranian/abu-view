// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Actor.h"
#include "AbuM53Component.h"
#include "ComponentReregisterContext.h"
#include "Engine/World.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/AutomationTest.h"
#include "Misc/Paths.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UnrealType.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
namespace
{
struct FAbuM53TestWorld
{
    UWorld* World=nullptr;
    FAbuM53TestWorld()
    {
        UWorld::InitializationValues IVS;
        IVS.AllowAudioPlayback(false).CreatePhysicsScene(false).CreateNavigation(false)
            .CreateAISystem(false).ShouldSimulatePhysics(false).SetTransactional(false).CreateFXSystem(false);
        World=UWorld::CreateWorld(EWorldType::Editor,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&IVS);
    }
    ~FAbuM53TestWorld() { if (World) World->DestroyWorld(false); }
};

UAbuM53Asset* MakeTestCloud(UObject* Outer,int32 PointCount=1)
{
    auto* Asset=NewObject<UAbuM53Asset>(Outer);
    Asset->Frames.SetNum(2);
    for (int32 I=0; I<2; ++I)
    {
        auto& Frame=Asset->Frames[I];
        Frame.TimeSeconds=I;
        Frame.SplatCount=PointCount;
        Frame.PackedPoints.SetNumZeroed(PointCount*sizeof(FAbuM53GPUPoint));
    }
    return Asset;
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53DetailsPersistenceTest,"AbuM53.Runtime.DetailsEditPersistence",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53DetailsPersistenceTest::RunTest(const FString& Parameters)
{
    FAbuM53TestWorld Scope;
    if (!TestNotNull(TEXT("isolated editor test world"),Scope.World)) return false;
    auto* Actor=Scope.World->SpawnActor<AAbuM53Actor>();
    if (!TestNotNull(TEXT("native splat actor"),Actor)) return false;
    TStrongObjectPtr<UAbuM53Asset> Asset(MakeTestCloud(GetTransientPackage()));
    Actor->SplatComponent->SetAsset(Asset.Get());
    auto Initial=Actor->SplatComponent->GetRenderPoints();
    TestTrue(TEXT("initial cloud is ready"),Initial.IsValid());
    {
        FComponentReregisterContext Reregister(Actor->SplatComponent);
    }
    TestTrue(TEXT("temporary unregister preserves the decoded allocation"),Actor->SplatComponent->GetRenderPoints()==Initial);

    auto Edit=[&](const TCHAR* Name,TFunctionRef<void(UAbuM53Component*)> Change)
    {
        auto* Component=Actor->SplatComponent.Get();
        FProperty* Property=FindFProperty<FProperty>(Component->GetClass(),Name);
        if (!TestNotNull(FString::Printf(TEXT("Details property %s exists"),Name),Property)) return;
        Component->PreEditChange(Property);
        Change(Component);
        FPropertyChangedEvent Event(Property,EPropertyChangeType::ValueSet);
        Component->PostEditChangeProperty(Event);
        Component=Actor->SplatComponent.Get();
        TestTrue(FString::Printf(TEXT("%s keeps assigned asset"),Name),Component->Asset==Asset.Get());
        TestTrue(FString::Printf(TEXT("%s keeps component registered"),Name),Component->IsRegistered());
        const auto Points=Component->GetRenderPoints();
        TestTrue(FString::Printf(TEXT("%s keeps render points available"),Name),Points.IsValid());
        TestEqual(FString::Printf(TEXT("%s preserves displayed count"),Name),Component->GetDisplayedSplatCount(),1);
    };
    Edit(TEXT("RelativeLocation"),[](auto* C){ C->SetRelativeLocation(FVector(10,20,30)); });
    Edit(TEXT("RelativeRotation"),[](auto* C){ C->SetRelativeRotation(FRotator(5,10,15)); });
    Edit(TEXT("RelativeScale3D"),[](auto* C){ C->SetRelativeScale3D(FVector(1.1)); });
    Edit(TEXT("UnitsToCentimeters"),[](auto* C){ C->UnitsToCentimeters=50; });
    Edit(TEXT("SourceAxes"),[](auto* C){ C->SourceAxes=EAbuM53SourceAxes::RawXYZ; });
    Edit(TEXT("Intensity"),[](auto* C){ C->Intensity=0.8f; });
    Edit(TEXT("OpacityMultiplier"),[](auto* C){ C->OpacityMultiplier=0.9f; });
    Edit(TEXT("SplatScale"),[](auto* C){ C->SplatScale=1.2f; });
    Edit(TEXT("MaxVisibleSplats"),[](auto* C){ C->MaxVisibleSplats=100; });
    Edit(TEXT("Backend"),[](auto* C){ C->Backend=EAbuM53Backend::GPU; });
    Edit(TEXT("bEnableCrop"),[](auto* C){ C->bEnableCrop=true; });
    Edit(TEXT("CropMin"),[](auto* C){ C->CropMin=FVector(-100); });
    Edit(TEXT("CropMax"),[](auto* C){ C->CropMax=FVector(100); });
    Edit(TEXT("TimeSeconds"),[](auto* C){ C->TimeSeconds=0.25; });
    Edit(TEXT("PlayRate"),[](auto* C){ C->PlayRate=0.5; });
    Edit(TEXT("bPlaying"),[](auto* C){ C->bPlaying=true; });
    Edit(TEXT("bLoop"),[](auto* C){ C->bLoop=false; });
    Edit(TEXT("bInterpolateStableIds"),[](auto* C){ C->bInterpolateStableIds=false; });
    Edit(TEXT("bStreamExternalSequences"),[](auto* C){ C->bStreamExternalSequences=false; });
    Edit(TEXT("StreamingCacheMiB"),[](auto* C){ C->StreamingCacheMiB=3072; });
    Actor->SetActorLocation(FVector(100,200,300));
    Actor->RerunConstructionScripts();
    TestTrue(TEXT("actor reconstruction keeps assigned asset"),Actor->SplatComponent->Asset==Asset.Get());
    TestTrue(TEXT("actor reconstruction keeps render points"),Actor->SplatComponent->GetRenderPoints().IsValid());
    TestEqual(TEXT("edited appearance is preserved"),Actor->SplatComponent->Intensity,0.8f);
    TestEqual(TEXT("edited budget is preserved"),Actor->SplatComponent->StreamingCacheMiB,3072);

    auto* Replacement=MakeTestCloud(Actor,2);
    Actor->SplatComponent->Asset=Replacement; // Direct reflected assignment, not SetAsset.
    TestEqual(TEXT("unresolved replacement has no displayed sample"),Actor->SplatComponent->GetDisplayedFrameIndex(),INDEX_NONE);
    const auto Replaced=Actor->SplatComponent->GetRenderPoints();
    TestTrue(TEXT("direct asset change invalidates prior cloud"),Replaced && Replaced->Num()==2);
    return true;
}

struct FAbuM53StreamCacheTestState
{
    TUniquePtr<FAbuM53TestWorld> Scope;
    AAbuM53Actor* Actor=nullptr;
    FAutomationTestBase* Test=nullptr;
    double Deadline=0;
    int32 Phase=0;
};
DEFINE_LATENT_AUTOMATION_COMMAND_ONE_PARAMETER(FAbuM53WaitForRetainedSequence,TSharedPtr<FAbuM53StreamCacheTestState>,State);
bool FAbuM53WaitForRetainedSequence::Update()
{
    auto* C=State->Actor->SplatComponent.Get();
    if (FPlatformTime::Seconds()>State->Deadline)
    {
        State->Test->AddError(FString::Printf(TEXT("Sequence cache test timed out: %s"),*C->LastStreamingError));
        return true;
    }
    // Exercise tick-driven paused loading; no render request is needed to complete seeks.
    C->TickComponent(0,LEVELTICK_All,nullptr);
    if (C->GetDisplayedFrameIndex()!=State->Phase) return false;
    State->Test->TestEqual(TEXT("ready frame contains the complete fixture"),C->GetDisplayedSplatCount(),1000);
    if (State->Phase<2)
    {
        ++State->Phase;
        C->Seek(C->Asset->Frames[State->Phase].TimeSeconds);
        return false;
    }
    if (C->IsLoadPending()) return false;
    State->Test->TestEqual(TEXT("three fitting frames are retained"),C->StreamingResidentBytes,int64(3*1000*sizeof(FAbuM53GPUPoint)));
    C->Seek(C->Asset->Frames[0].TimeSeconds);
    const auto Before=C->GetRenderPoints();
    State->Test->TestEqual(TEXT("loop wrap immediately displays cached first frame"),C->GetDisplayedFrameIndex(),0);
    State->Test->TestFalse(TEXT("loop wrap requires no disk decode"),C->IsLoadPending());
    {
        FComponentReregisterContext Reregister(C);
    }
    State->Test->TestTrue(TEXT("Details re-register keeps external sample allocation"),C->GetRenderPoints()==Before);
    State->Test->TestEqual(TEXT("Details re-register keeps complete sequence cache"),C->StreamingResidentBytes,int64(3*1000*sizeof(FAbuM53GPUPoint)));
    State->Test->TestTrue(TEXT("retained bytes stay within configured budget"),C->StreamingResidentBytes<=int64(C->StreamingCacheMiB)*1024*1024);
    // Changing a source through reflection must never reuse a frame with the same index.
    C->Asset=MakeTestCloud(State->Actor,2);
    State->Test->TestEqual(TEXT("old external sample is not reported for new asset"),C->GetDisplayedFrameIndex(),INDEX_NONE);
    const auto Replacement=C->GetRenderPoints();
    State->Test->TestTrue(TEXT("direct source change replaces external data"),Replacement && Replacement->Num()==2);
    State->Test->TestEqual(TEXT("source replacement releases external cache accounting"),C->StreamingResidentBytes,int64(0));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53RetainedSequenceTest,"AbuM53.Runtime.RetainedSequenceCache",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FAbuM53RetainedSequenceTest::RunTest(const FString& Parameters)
{
    const auto Plugin=IPluginManager::Get().FindPlugin(TEXT("AbuM53"));
    if (!Plugin) return false;
    FAbuM53ImportResult Index;
    FString Error;
    if (!TestTrue(TEXT("fixture sequence index reads"),AbuM53::ReadSequenceIndex(FPaths::Combine(Plugin->GetBaseDir(),TEXT("Tests/Fixtures/shell.am53seq")),Index,Error))) return false;
    auto State=MakeShared<FAbuM53StreamCacheTestState>();
    State->Scope=MakeUnique<FAbuM53TestWorld>();
    if (!TestNotNull(TEXT("isolated stream world"),State->Scope->World)) return false;
    State->Actor=State->Scope->World->SpawnActor<AAbuM53Actor>();
    if (!TestNotNull(TEXT("stream test actor"),State->Actor)) return false;
    auto* Asset=NewObject<UAbuM53Asset>(State->Actor);
    Asset->ReplaceData(MoveTemp(Index));
    State->Actor->SplatComponent->SetAsset(Asset);
    State->Actor->SplatComponent->StreamingCacheMiB=16;
    State->Deadline=FPlatformTime::Seconds()+30;
    State->Test=this;
    ADD_LATENT_AUTOMATION_COMMAND(FAbuM53WaitForRetainedSequence(State));
    return true;
}
#endif
