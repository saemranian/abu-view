// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AbuM53Types.h"
#include "AbuM53Asset.generated.h"

UCLASS(BlueprintType)
class ABUM53RUNTIME_API UAbuM53Asset : public UObject
{
    GENERATED_BODY()
public:
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Source") FString SourceFilename;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Source") FString CoordinateProfile;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Source", meta=(MultiLine=true)) FString ImportReport;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Animation") double FramesPerSecond = 30;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Animation") bool bStableIds = false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Streaming") bool bExternalStream = false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Animation") TArray<FAbuM53Frame> Frames;
    UPROPERTY(Transient) int32 DataRevision = 0;

    UFUNCTION(BlueprintPure, Category="Abu M53") int32 GetFrameCount() const { return Frames.Num(); }
    UFUNCTION(BlueprintPure, Category="Abu M53") int32 GetSplatCount() const { return Frames.IsEmpty() ? 0 : Frames[0].SplatCount; }
    UFUNCTION(BlueprintPure, Category="Abu M53") double GetDuration() const;
    UFUNCTION(BlueprintPure, Category="Abu M53") int32 FindFrame(double TimeSeconds) const;
    UFUNCTION(BlueprintPure, Category="Abu M53") int64 GetDecodedBytes() const;
    bool ImportFile(const FString& Filename, FString& Error);
    void ReplaceData(FAbuM53ImportResult&& Result);
    TSharedPtr<const TArray<FAbuM53GPUPoint>, ESPMode::ThreadSafe> GetFramePoints(int32 FrameIndex) const;
    virtual void PostLoad() override;
private:
    mutable TMap<int32, TWeakPtr<const TArray<FAbuM53GPUPoint>, ESPMode::ThreadSafe>> FrameCache;
};
