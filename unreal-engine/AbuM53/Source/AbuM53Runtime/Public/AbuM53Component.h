// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "AbuM53Asset.h"
#include "AbuM53Component.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FAbuM53LoadCompleted, bool, bSuccess, FString, Message);
struct FAbuM53StreamFrame;
struct FAbuM53AsyncGate;

UCLASS(ClassGroup=(Rendering), BlueprintType, meta=(BlueprintSpawnableComponent))
class ABUM53RUNTIME_API UAbuM53Component : public USceneComponent
{
    GENERATED_BODY()
public:
    UAbuM53Component();
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53") TObjectPtr<UAbuM53Asset> Asset;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Transform", meta=(ClampMin="0.000001")) float UnitsToCentimeters = 100;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Transform") EAbuM53SourceAxes SourceAxes = EAbuM53SourceAxes::Auto;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Interp, Category="Abu M53|Appearance", meta=(ClampMin="0")) float Intensity = 1;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Interp, Category="Abu M53|Appearance", meta=(ClampMin="0",ClampMax="1")) float OpacityMultiplier = 1;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Interp, Category="Abu M53|Appearance", meta=(ClampMin="0.001")) float SplatScale = 1;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Performance", meta=(ClampMin="1",ClampMax="20000000")) int32 MaxVisibleSplats = 5000000;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Performance") EAbuM53Backend Backend = EAbuM53Backend::Auto;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Crop") bool bEnableCrop = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Crop") FVector CropMin = FVector(-1000000);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Crop") FVector CropMax = FVector(1000000);
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Interp, Category="Abu M53|Animation") double TimeSeconds = 0;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Animation") double PlayRate = 1;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Animation") bool bPlaying = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Animation") bool bLoop = true;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Animation") bool bInterpolateStableIds = true;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Streaming") bool bStreamExternalSequences = true;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Abu M53|Streaming", meta=(ClampMin="16",ClampMax="8192",ToolTip="Decoded frame cache budget. Reserve room for at least three frames; 3072 MiB supports three 3-million-splat frames. Temporary decoding and GPU buffers use additional memory.")) int32 StreamingCacheMiB = 512;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Abu M53|Streaming") int64 StreamingResidentBytes = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Abu M53|Streaming") int64 StreamingMisses = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Abu M53|Streaming") FString LastStreamingError;
    UPROPERTY(BlueprintAssignable, Category="Abu M53") FAbuM53LoadCompleted OnLoadCompleted;

    UFUNCTION(BlueprintCallable, Category="Abu M53") void SetAsset(UAbuM53Asset* InAsset);
    UFUNCTION(BlueprintCallable, Category="Abu M53") void Play() { bPlaying = true; }
    UFUNCTION(BlueprintCallable, Category="Abu M53") void Pause() { bPlaying = false; }
    UFUNCTION(BlueprintCallable, Category="Abu M53") void Seek(double Seconds);
    UFUNCTION(BlueprintCallable, Category="Abu M53") void LoadFileAsync(const FString& Filename);
    UFUNCTION(BlueprintCallable, Category="Abu M53") void CancelLoad();
    UFUNCTION(BlueprintPure, Category="Abu M53") bool IsLoadPending() const;
    UFUNCTION(BlueprintPure, Category="Abu M53") int32 GetCurrentFrameIndex() const;
    // Ready sample selected for drawing; distinct from a requested seek target.
    UFUNCTION(BlueprintPure, Category="Abu M53|Streaming") int32 GetDisplayedFrameIndex() const;
    UFUNCTION(BlueprintPure, Category="Abu M53|Streaming") int32 GetDisplayedSplatCount() const;
    UFUNCTION(BlueprintPure, Category="Abu M53") FVector GetSourceOrigin() const;
    FMatrix GetSourceAxisMatrix() const;
    static const TArray<TWeakObjectPtr<UAbuM53Component>>& GetRegisteredComponents();
    TSharedPtr<const TArray<FAbuM53GPUPoint>, ESPMode::ThreadSafe> GetRenderPoints() const;

    virtual void OnRegister() override;
    virtual void OnUnregister() override;
    virtual void OnComponentDestroyed(bool bDestroyingHierarchy) override;
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
private:
    uint64 LoadGeneration = 0;
    mutable TSharedPtr<const TArray<FAbuM53GPUPoint>, ESPMode::ThreadSafe> CachedPoints;
    mutable TWeakObjectPtr<UAbuM53Asset> CachedAsset;
    mutable int32 CachedRevision = INDEX_NONE;
    mutable int32 CachedFrame = INDEX_NONE;
    mutable bool bCachedInterpolation = false;
    mutable double CachedTime = TNumericLimits<double>::Lowest();
    TMap<int32,TSharedPtr<FAbuM53StreamFrame,ESPMode::ThreadSafe>> StreamCache;
    TMap<int32,uint64> StreamLastUse;
    uint64 StreamUseCounter = 0;
    TSet<int32> StreamPending;
    TSet<int32> StreamFailed;
    TSharedPtr<FAbuM53StreamFrame,ESPMode::ThreadSafe> DisplayedStreamFrame;
    uint64 StreamSeekEpoch = 0;
    int32 StreamLastRequestFrame = INDEX_NONE;
    TSharedPtr<FAbuM53AsyncGate,ESPMode::ThreadSafe> AsyncGate;
    bool bLoadQueued = false;
    bool bQueuedStreaming = false;
    FString QueuedFilename;
    uint64 QueuedGeneration = 0;
    TWeakObjectPtr<UAbuM53Asset> ObservedAsset;
    int32 ObservedRevision = INDEX_NONE;
    int32 ObservedCacheMiB = 512;
    void SynchronizeSourceState();
    void ResetRenderCache();
    void TrimStreamCache(int64 BudgetBytes);
    int64 GetStreamingBudgetBytes() const;
    void StartQueuedLoad();
    void RequestStreamFrames();
    void RequestStreamFrame(int32 Index);
};
