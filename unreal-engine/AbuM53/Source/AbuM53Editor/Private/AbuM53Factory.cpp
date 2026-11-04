// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Factory.h"
#include "AbuM53Asset.h"
#include "Misc/Paths.h"
#include "Misc/FeedbackContext.h"
#include "Misc/ScopedSlowTask.h"
#include "Misc/ScopeLock.h"
#include "Async/Async.h"

namespace
{
bool DecodeWithProgress(const FString& Filename, FAbuM53ImportResult& Result, FString& Error,
    FFeedbackContext* Warn, bool& bCanceled)
{
    check(IsInGameThread());
    bCanceled = false;
    TAtomic<bool> CancelRequested(false);
    FCriticalSection MessageMutex;
    FString Message = FString::Printf(TEXT("Reading %s"), *FPaths::GetCleanFilename(Filename));
    // Stage messages are truthful; a data-dependent decode has no reliable percent.
    FScopedSlowTask Progress(1, FText::FromString(Message), !IsRunningCommandlet(), Warn ? *Warn : *GWarn);
    Progress.MakeDialogDelayed(0.25f, true);
    const double Started = FPlatformTime::Seconds();
    // Decode produces data only. The UObject is created/replaced on the game thread
    // after success. Always join this worker before captured references leave scope.
    TFuture<bool> Future = Async(EAsyncExecution::ThreadPool, [&Result, &Error, &CancelRequested, &MessageMutex, &Message, Filename]()
    {
        FAbuM53ImportFeedback Feedback;
        Feedback.ShouldCancel = [&CancelRequested]() { return CancelRequested.Load(); };
        Feedback.ReportProgress = [&MessageMutex, &Message](const FString& NewMessage)
        {
            FScopeLock Lock(&MessageMutex);
            Message = NewMessage;
        };
        return AbuM53::DecodeFile(Filename, Result, Error, 1024ll * 1024 * 1024, &Feedback);
    });
    while (!Future.WaitFor(FTimespan::FromMilliseconds(33)))
    {
        FString CurrentMessage;
        {
            FScopeLock Lock(&MessageMutex);
            CurrentMessage = Message;
        }
        if (CancelRequested.Load()) CurrentMessage = TEXT("Canceling Abu M53 import...");
        Progress.EnterProgressFrame(0, FText::FromString(CurrentMessage));
        if (Progress.ShouldCancel()) CancelRequested.Store(true);
    }
    const bool bDecoded = Future.Get();
    bCanceled = CancelRequested.Load() || Progress.ShouldCancel();
    if (bCanceled)
    {
        Result = FAbuM53ImportResult();
        Error = TEXT("Import canceled; existing asset retained.");
        return false;
    }
    if (bDecoded)
    {
        UE_LOG(LogTemp, Display, TEXT("Abu M53 import completed in %.3f s: %s (%d frame(s))."),
            FPlatformTime::Seconds() - Started, *Filename, Result.Frames.Num());
    }
    return bDecoded;
}
}

UAbuM53Factory::UAbuM53Factory()
{
    SupportedClass=UAbuM53Asset::StaticClass();
    bCreateNew=false;
    bEditorImport=true;
    Formats.Add(TEXT("ply;Gaussian Splat PLY"));
    Formats.Add(TEXT("splat;Gaussian Splat Binary"));
    Formats.Add(TEXT("spz;Gaussian SPZ (version-specific codec support)"));
    Formats.Add(TEXT("am53;Abu M53 Container"));
    Formats.Add(TEXT("am53seq;Abu M53 Animation Sequence"));
    Formats.Add(TEXT("json;Abu M53 / AbuAlign Sequence Manifest"));
    ImportPriority=DefaultImportPriority+10;
}

bool UAbuM53Factory::FactoryCanImport(const FString& Filename)
{
    const FString Extension=FPaths::GetExtension(Filename).ToLower();
    return Extension==TEXT("ply") || Extension==TEXT("splat") || Extension==TEXT("spz") || Extension==TEXT("am53") || Extension==TEXT("am53seq") ||
        (Extension==TEXT("json") && (FPaths::GetBaseFilename(Filename).Contains(TEXT("sequence")) || FPaths::GetBaseFilename(Filename).Contains(TEXT("am53"))));
}

UObject* UAbuM53Factory::FactoryCreateFile(UClass* InClass,UObject* InParent,FName InName,EObjectFlags Flags,
    const FString& Filename,const TCHAR* Parms,FFeedbackContext* Warn,bool& bOutOperationCanceled)
{
    bOutOperationCanceled=false;
    FAbuM53ImportResult Result;
    FString Error;
    if (!DecodeWithProgress(Filename,Result,Error,Warn,bOutOperationCanceled))
    {
        if (Warn && !bOutOperationCanceled) Warn->Logf(ELogVerbosity::Error,TEXT("Abu M53: %s"),*Error);
        return nullptr;
    }
    auto* Asset=NewObject<UAbuM53Asset>(InParent,InClass,InName,Flags);
    Asset->ReplaceData(MoveTemp(Result));
    return Asset;
}

bool UAbuM53Factory::CanReimport(UObject* Obj,TArray<FString>& OutFilenames)
{
    if (auto* Asset=Cast<UAbuM53Asset>(Obj))
    {
        if (!Asset->SourceFilename.IsEmpty()) { OutFilenames.Add(Asset->SourceFilename); return true; }
    }
    return false;
}
void UAbuM53Factory::SetReimportPaths(UObject* Obj,const TArray<FString>& Paths)
{
    if (auto* Asset=Cast<UAbuM53Asset>(Obj); Asset && Paths.Num()==1) Asset->SourceFilename=Paths[0];
}
EReimportResult::Type UAbuM53Factory::Reimport(UObject* Obj)
{
    auto* Asset=Cast<UAbuM53Asset>(Obj);
    if (!Asset) return EReimportResult::Failed;
    FString Error;
    FAbuM53ImportResult Result;
    bool bCanceled = false;
    if (!DecodeWithProgress(Asset->SourceFilename,Result,Error,GWarn,bCanceled))
    {
        if (bCanceled) return EReimportResult::Cancelled;
        UE_LOG(LogTemp,Error,TEXT("Abu M53 reimport failed; old asset retained: %s"),*Error);
        return EReimportResult::Failed;
    }
    Asset->ReplaceData(MoveTemp(Result));
    Asset->MarkPackageDirty();
    return EReimportResult::Succeeded;
}
