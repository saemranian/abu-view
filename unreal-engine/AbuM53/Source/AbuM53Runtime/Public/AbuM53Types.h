// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CoreMinimal.h"
#include "AbuM53Types.generated.h"

// Byte-identical with the shader input. SH is coefficient-major RGB, flattened.
struct alignas(16) ABUM53RUNTIME_API FAbuM53GPUPoint
{
    FVector4f PositionOpacity = FVector4f(0,0,0,1);
    FVector4f ScaleDegree = FVector4f(1,1,1,0);
    FVector4f Rotation = FVector4f(0,0,0,1);
    FVector4f SH[12];
    FVector4f Metadata = FVector4f(0,0,0,0);
    FAbuM53GPUPoint() { for (FVector4f& Band : SH) Band=FVector4f(0,0,0,0); }
};
static_assert(sizeof(FAbuM53GPUPoint) == 256, "Abu M53 GPU layout changed");

UENUM(BlueprintType)
enum class EAbuM53Backend : uint8 { Auto, GPU, CPUAssisted, Software };

UENUM(BlueprintType)
enum class EAbuM53SourceAxes : uint8 { Auto, RawXYZ, RightUpBack };

USTRUCT(BlueprintType)
struct ABUM53RUNTIME_API FAbuM53Frame
{
    GENERATED_BODY()
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Abu M53") double TimeSeconds = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Abu M53") int32 SplatCount = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Abu M53") int32 SHDegree = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Abu M53") FVector SourceOrigin = FVector::ZeroVector;
    UPROPERTY() FBox SourceBounds = FBox(ForceInit);
    UPROPERTY() TArray<uint8> PackedPoints;
    UPROPERTY() FString ExternalFilename;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Source") FString SourceCoordinateProfile = TEXT("unspecified");
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Source") bool bSourceAntialiased = false;

    // Package payloads use one contiguous write. Legacy tagged packages remain readable.
    bool Serialize(FArchive& Ar);
};

template<> struct TStructOpsTypeTraits<FAbuM53Frame> : TStructOpsTypeTraitsBase2<FAbuM53Frame>
{
    enum { WithSerializer = true };
};

struct ABUM53RUNTIME_API FAbuM53ImportResult
{
    TArray<FAbuM53Frame> Frames;
    FString SourceFilename;
    FString CoordinateProfile = TEXT("source_xyz");
    FString ImportReport;
    double FramesPerSecond = 30;
    bool bStableIds = false;
    bool bExternalStream = false;
};

// Optional data-only callbacks. They run on the thread that calls DecodeFile;
// callbacks must not access UObjects or editor UI when decoding on a worker.
struct ABUM53RUNTIME_API FAbuM53ImportFeedback
{
    TFunction<bool()> ShouldCancel;
    TFunction<void(const FString&)> ReportProgress;
};

namespace AbuM53
{
    // Data-only operation, safe on worker threads. Never creates UObject instances.
    ABUM53RUNTIME_API bool DecodeFile(const FString& Filename, FAbuM53ImportResult& Result,
        FString& Error, int64 MaxDecodedBytes = 1024ll * 1024 * 1024,
        const FAbuM53ImportFeedback* Feedback = nullptr);
    ABUM53RUNTIME_API bool ReadSequenceIndex(const FString& Filename, FAbuM53ImportResult& Result, FString& Error);
}
