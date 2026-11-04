// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Shaders.h"
#include "AbuM53Types.h"
#include "Misc/AutomationTest.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RenderingThread.h"
#include "RHIGPUReadback.h"

#if WITH_DEV_AUTOMATION_TESTS
namespace
{
struct FProjectionCase
{
    const TCHAR* Name;
    FMatrix44f Projection;
    FAbuM53GPUPoint Point;
    bool bVisible = false;
    FVector4f MeanRadius = FVector4f(0, 0, 0, 0);
    FVector4f Conic = FVector4f(0, 0, 0, 0);
    float Depth = 0;
};

FProjectionCase MakeProjectionCase(const TCHAR* Name, const FMatrix44f& Projection,
    FVector3f Position, FVector3f Scale)
{
    FProjectionCase Result;
    Result.Name = Name;
    Result.Projection = Projection;
    Result.Point.PositionOpacity = FVector4f(Position, 0.5f);
    Result.Point.ScaleDegree = FVector4f(Scale, 0);
    return Result;
}

void ExpectVisible(FProjectionCase& Case, FVector2f Mean, double XX, double XY, double YY, float Depth)
{
    // Analytic covariance entries supplied by each fixture; no shader projection
    // code is reused in the oracle. Invert the symmetric 2x2 covariance directly.
    const double Determinant = XX * YY - XY * XY;
    Case.bVisible = true;
    Case.MeanRadius = FVector4f(Mean.X, Mean.Y, float(3 * FMath::Sqrt(XX)), float(3 * FMath::Sqrt(YY)));
    Case.Conic = FVector4f(float(YY / Determinant), float(-XY / Determinant), float(XX / Determinant), 0.5f);
    Case.Depth = Depth;
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAbuM53ProjectionGPUValidation, "AbuM53.Render.ProjectionGPU",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter | EAutomationTestFlags::NonNullRHI)
bool FAbuM53ProjectionGPUValidation::RunTest(const FString& Parameters)
{
    if (GUsingNullRHI || !IsFeatureLevelSupported(GMaxRHIShaderPlatform, ERHIFeatureLevel::SM5))
    {
        AddError(TEXT("ProjectionGPU requires an active SM5+ rendering device"));
        return false;
    }
    // Row-vector projection: clip=(x,y,near,z), infinite reversed-Z perspective.
    const FMatrix44f Perspective(FPlane4f(1, 0, 0, 0), FPlane4f(0, 1, 0, 0),
        FPlane4f(0, 0, 0, 1), FPlane4f(0, 0, 0.1f, 0));
    const FMatrix44f FinitePerspective(FPlane4f(1, 0, 0, 0), FPlane4f(0, 1, 0, 0),
        FPlane4f(0, 0, -0.1f / 9.9f, 1), FPlane4f(0, 0, 1.f / 9.9f, 0));
    const FMatrix44f Orthographic(FPlane4f(1, 0, 0, 0), FPlane4f(0, 1, 0, 0),
        FPlane4f(0, 0, -1.f / 9.9f, 0), FPlane4f(0, 0, 10.f / 9.9f, 1));
    TArray<FProjectionCase> Cases;
    auto& Central = Cases.Add_GetRef(MakeProjectionCase(TEXT("in-frustum perspective"), Perspective, FVector3f(0, 0, 2), FVector3f(0.1f, 0.2f, 0.3f)));
    ExpectVisible(Central, FVector2f(480, 270), 24.0 * 24.0 + 0.3, 0, 27.0 * 27.0 + 0.3, 0.05f);
    Cases.Add(MakeProjectionCase(TEXT("center before near plane"), Perspective, FVector3f(0, 0, 0.05f), FVector3f(0.01f)));
    Cases.Add(MakeProjectionCase(TEXT("center behind camera"), Perspective, FVector3f(0, 0, -2), FVector3f(0.1f)));
    auto& Near = Cases.Add_GetRef(MakeProjectionCase(TEXT("center on near plane"), Perspective, FVector3f(0, 0, 0.1f), FVector3f(0.001f)));
    ExpectVisible(Near, FVector2f(480, 270), 4.8 * 4.8 + 0.3, 0, 2.7 * 2.7 + 0.3, 1.f);
    // A source centimeter-sized and hundreds of frustum widths away must not
    // cover the screen through a perspective derivative singularity.
    Cases.Add(MakeProjectionCase(TEXT("extreme off-axis near-center cannot cover screen"), Perspective,
        FVector3f(100, 1, 0.11f), FVector3f(0.01f, 0.01f, 0.1f)));
    auto& OffAxis = Cases.Add_GetRef(MakeProjectionCase(TEXT("guard-band covariance with unchanged mean"), Perspective,
        FVector3f(1.5f, 0.7f, 1), FVector3f(0.3f, 0.1f, 0.8f)));
    // Jx=(480,0,-480*1.3), Jy=(0,-270,270*0.7), with diagonal source covariance.
    ExpectVisible(OffAxis, FVector2f(1200, 81), 144.0 * 144.0 + 499.2 * 499.2 + 0.3,
        -499.2 * 151.2, 27.0 * 27.0 + 151.2 * 151.2 + 0.3, 0.1f);
    Cases.Add(MakeProjectionCase(TEXT("center beyond finite far plane"), FinitePerspective, FVector3f(0, 0, 11), FVector3f(0.1f)));
    auto& Ortho = Cases.Add_GetRef(MakeProjectionCase(TEXT("orthographic off-axis derivative remains exact"), Orthographic,
        FVector3f(1.5f, 0, 2), FVector3f(0.6f, 0.2f, 5)));
    ExpectVisible(Ortho, FVector2f(1200, 270), 288.0 * 288.0 + 0.3, 0, 54.0 * 54.0 + 0.3, 8.f / 9.9f);

    TArray<FString> Failures;
    const int32 CaseCount = Cases.Num();
    ENQUEUE_RENDER_COMMAND(AbuM53ProjectionReadbackTest)([Cases = MoveTemp(Cases), &Failures](FRHICommandListImmediate& Cmd)
    {
        FViewUniformShaderParameters ViewParameters;
        ViewParameters.PreExposure = 1;
        const auto View = TUniformBufferRef<FViewUniformShaderParameters>::CreateUniformBufferImmediate(ViewParameters, UniformBuffer_SingleFrame);
        auto* ShaderMap = GetGlobalShaderMap(GMaxRHIFeatureLevel);
        for (const FProjectionCase& Case : Cases)
        {
            FRHIGPUBufferReadback Readback(TEXT("AbuM53.ProjectionReadback"));
            FRDGBuilder Graph(Cmd);
            auto* Source = CreateStructuredBuffer(Graph, TEXT("AbuM53.TestProjectionSource"), 16, 16,
                &Case.Point, sizeof(Case.Point), ERDGInitialDataFlags::NoCopy);
            auto ProjectedDesc = FRDGBufferDesc::CreateStructuredDesc(16, 3);
            ProjectedDesc.Usage |= BUF_SourceCopy;
            auto* Projected = Graph.CreateBuffer(ProjectedDesc, TEXT("AbuM53.TestProjectionOutput"));
            auto* Keys = Graph.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(8, 1), TEXT("AbuM53.TestProjectionKeys"));
            auto* P = Graph.AllocParameters<FAbuM53ProjectCS::FParameters>();
            P->PointCount = 1;
            P->OutputOffset = 0;
            P->LocalToClip = Case.Projection;
            P->LocalToView = FMatrix44f::Identity;
            P->CameraLocal = FVector3f::ZeroVector;
            P->ViewSize = FVector2f(960, 540);
            P->Intensity = P->OpacityMultiplier = P->SplatScale = 1;
            P->FilterVariance = 0.3f;
            P->View = View;
            P->CropEnabled = 0;
            P->CropMin = P->CropMax = FVector3f::ZeroVector;
            P->SourcePoints = Graph.CreateSRV(Source);
            P->Projected = Graph.CreateUAV(Projected);
            P->KeysOut = Graph.CreateUAV(Keys);
            FComputeShaderUtils::AddPass(Graph, RDG_EVENT_NAME("AbuM53.TestProjection"), TShaderMapRef<FAbuM53ProjectCS>(ShaderMap), P, FIntVector(1, 1, 1));
            AddEnqueueCopyPass(Graph, &Readback, Projected, 3 * sizeof(FVector4f));
            Graph.Execute();
            Cmd.SubmitAndBlockUntilGPUIdle();
            if (!Readback.IsReady()) { Failures.Add(FString::Printf(TEXT("%s: readback not ready"), Case.Name)); continue; }
            const auto* Actual = static_cast<const FVector4f*>(Readback.Lock(3 * sizeof(FVector4f)));
            if (!Actual) { Failures.Add(FString::Printf(TEXT("%s: cannot map readback"), Case.Name)); continue; }
            if (!Case.bVisible)
            {
                for (int32 I = 0; I < 3; ++I)
                    if (Actual[I] != FVector4f(0, 0, 0, 0)) Failures.Add(FString::Printf(TEXT("%s: rejected point was projected"), Case.Name));
            }
            else
            {
                auto Compare = [&](float Value, float Expected, const TCHAR* Label)
                {
                    const float Tolerance = FMath::Max(1.e-7f, FMath::Abs(Expected) * 2.e-4f);
                    if (!FMath::IsFinite(Value) || FMath::Abs(Value - Expected) > Tolerance)
                        Failures.Add(FString::Printf(TEXT("%s: %s got %.9g expected %.9g"), Case.Name, Label, Value, Expected));
                };
                for (int32 I = 0; I < 4; ++I)
                {
                    Compare(Actual[0][I], Case.MeanRadius[I], TEXT("mean/radius"));
                    Compare(Actual[1][I], Case.Conic[I], TEXT("conic/alpha"));
                }
                Compare(Actual[2].W, Case.Depth, TEXT("clip depth"));
            }
            Readback.Unlock();
        }
    });
    FlushRenderingCommands();
    for (const FString& Failure : Failures) AddError(Failure);
    AddInfo(FString::Printf(TEXT("Compared GPU projected mean, covariance inverse, radius, opacity and depth across %d analytic clipping/projection cases"), CaseCount));
    return Failures.IsEmpty();
}
#endif
