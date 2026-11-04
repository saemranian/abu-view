// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
#include "Factories/Factory.h"
#include "EditorReimportHandler.h"
#include "AbuM53Factory.generated.h"

UCLASS()
class ABUM53EDITOR_API UAbuM53Factory : public UFactory, public FReimportHandler
{
    GENERATED_BODY()
public:
    UAbuM53Factory();
    virtual bool FactoryCanImport(const FString& Filename) override;
    virtual UObject* FactoryCreateFile(UClass* InClass,UObject* InParent,FName InName,EObjectFlags Flags,
        const FString& Filename,const TCHAR* Parms,FFeedbackContext* Warn,bool& bOutOperationCanceled) override;
    virtual bool CanReimport(UObject* Obj,TArray<FString>& OutFilenames) override;
    virtual void SetReimportPaths(UObject* Obj,const TArray<FString>& NewReimportPaths) override;
    virtual EReimportResult::Type Reimport(UObject* Obj) override;
};
