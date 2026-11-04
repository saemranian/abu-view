// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Shaders.h"
#include "AbuM53Tiles.h"
#include "AbuM53Scan.h"
#include "AbuM53SourceCache.h"
#include "AbuM53Component.h"
#include "AbuM53/Core.h"
#include "CommonRenderResources.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/CoreDelegates.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "PipelineStateCache.h"
#include "RHIStaticStates.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RendererInterface.h"
#include "SceneInterface.h"
#include "SceneViewExtension.h"
#include "ShaderCompilerCore.h"
#include "Math/ScaleMatrix.h"
#include "Math/TranslationMatrix.h"
#include "ProfilingDebugging/RealtimeGPUProfiler.h"
#include "ProfilingDebugging/CsvProfiler.h"

DEFINE_LOG_CATEGORY_STATIC(LogAbuM53Render, Log, All);
DECLARE_GPU_STAT_NAMED(AbuM53, TEXT("Abu M53"));
CSV_DEFINE_CATEGORY(AbuM53, true);

// Diagonalize a transformed covariance so the portable renderer sees the same
// affine ellipsoid as the GPU, including reflected axes and nonuniform scale.
static void M53TransformShape(const FMatrix& World,const FAbuM53GPUPoint& P,double Scale,abum53::Gaussian& G)
{
    FQuat Q(P.Rotation.X,P.Rotation.Y,P.Rotation.Z,P.Rotation.W);
    FVector Axes[3]={FVector(World.TransformVector(Q.RotateVector(FVector(P.ScaleDegree.X*Scale,0,0)))),FVector(World.TransformVector(Q.RotateVector(FVector(0,P.ScaleDegree.Y*Scale,0)))),FVector(World.TransformVector(Q.RotateVector(FVector(0,0,P.ScaleDegree.Z*Scale))))};
    double A[3][3]={},V[3][3]={{1,0,0},{0,1,0},{0,0,1}};
    for(int i=0;i<3;i++)for(int j=0;j<3;j++)for(int k=0;k<3;k++)A[i][j]+=Axes[k][i]*Axes[k][j];
    for(int iteration=0;iteration<24;iteration++)
    {
        int p=0,q=1;for(int i=0;i<3;i++)for(int j=i+1;j<3;j++)if(FMath::Abs(A[i][j])>FMath::Abs(A[p][q])){p=i;q=j;}
        if(FMath::Abs(A[p][q])<1e-14)break;
        const double Angle=0.5*FMath::Atan2(2*A[p][q],A[q][q]-A[p][p]),C=FMath::Cos(Angle),S=FMath::Sin(Angle);
        const double App=A[p][p],Aqq=A[q][q],Apq=A[p][q];
        for(int k=0;k<3;k++)if(k!=p&&k!=q){double Kp=A[k][p],Kq=A[k][q];A[k][p]=A[p][k]=C*Kp-S*Kq;A[k][q]=A[q][k]=S*Kp+C*Kq;}
        A[p][p]=C*C*App-2*S*C*Apq+S*S*Aqq;A[q][q]=S*S*App+2*S*C*Apq+C*C*Aqq;A[p][q]=A[q][p]=0;
        for(int k=0;k<3;k++){double Kp=V[k][p],Kq=V[k][q];V[k][p]=C*Kp-S*Kq;V[k][q]=S*Kp+C*Kq;}
    }
    FVector X(V[0][0],V[1][0],V[2][0]),Y(V[0][1],V[1][1],V[2][1]),Z(V[0][2],V[1][2],V[2][2]);
    if(FVector::DotProduct(FVector::CrossProduct(X,Y),Z)<0)X=-X;
    FMatrix Rotation(FPlane(X,0),FPlane(Y,0),FPlane(Z,0),FPlane(0,0,0,1));FQuat Out(Rotation);Out.Normalize();
    G.rotation[0]=Out.X;G.rotation[1]=Out.Y;G.rotation[2]=Out.Z;G.rotation[3]=Out.W;
    for(int k=0;k<3;k++)G.scale[k]=FMath::Sqrt(FMath::Max(A[k][k],1e-20));
}
IMPLEMENT_GLOBAL_SHADER(FAbuM53ProjectCS, "/Plugin/AbuM53/Private/AbuM53.usf", "ProjectCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FAbuM53HistogramCS, "/Plugin/AbuM53/Private/AbuM53.usf", "HistogramCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FAbuM53ScatterCS, "/Plugin/AbuM53/Private/AbuM53.usf", "ScatterCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FAbuM53DrawVS, "/Plugin/AbuM53/Private/AbuM53.usf", "DrawVS", SF_Vertex);
IMPLEMENT_GLOBAL_SHADER(FAbuM53DrawPS, "/Plugin/AbuM53/Private/AbuM53.usf", "DrawPS", SF_Pixel);
IMPLEMENT_GLOBAL_SHADER(FAbuM53SoftwareVS, "/Plugin/AbuM53/Private/AbuM53.usf", "SoftwareVS", SF_Vertex);
IMPLEMENT_GLOBAL_SHADER(FAbuM53SoftwarePS, "/Plugin/AbuM53/Private/AbuM53.usf", "SoftwarePS", SF_Pixel);

static TAutoConsoleVariable<int32> CVarM53Enable(TEXT("r.AbuM53.Enable"),1,TEXT("Enable Abu M53 rendering."),ECVF_RenderThreadSafe);
static TAutoConsoleVariable<int32> CVarM53Max(TEXT("r.AbuM53.MaxSplats"),5000000,TEXT("Hard per-view selected splat budget; excess points are omitted with a warning."),ECVF_RenderThreadSafe);
static TAutoConsoleVariable<float> CVarM53Filter(TEXT("r.AbuM53.FilterVariance"),0.3f,TEXT("Screen-space filter variance in square pixels."),ECVF_RenderThreadSafe);
static TAutoConsoleVariable<float> CVarM53Cutoff(TEXT("r.AbuM53.AlphaCutoff"),1.0f/255.0f,TEXT("Raster alpha rejection threshold."),ECVF_RenderThreadSafe);
static TAutoConsoleVariable<int32> CVarM53Backend(TEXT("r.AbuM53.Backend"),0,TEXT("0=component setting/GPU, 1=GPU, 2=CPU sort/GPU draw, 3=CPU software diagnostic preview."),ECVF_RenderThreadSafe);
static TAutoConsoleVariable<int32> CVarM53Tiles(TEXT("r.AbuM53.Tiles"),1,TEXT("Use bounded tiled compute with whole-view sorted-quad fallback on overflow."),ECVF_RenderThreadSafe);
static TAutoConsoleVariable<int32> CVarM53SourceCache(TEXT("r.AbuM53.SourceCacheMiB"),2048,TEXT("Global retained GPU source-buffer budget in MiB (0 disables retention, maximum 8192). Use 3072 for three 3-million-splat samples. Sorting, rasterization and active graph uploads use additional memory."),ECVF_RenderThreadSafe);

struct FM53Snapshot
{
    uint32 Id=0;
    TSharedPtr<const TArray<FAbuM53GPUPoint>,ESPMode::ThreadSafe> Points;
    FTransform Transform;
    FMatrix SourceBasis=FMatrix::Identity;
    FVector Origin=FVector::ZeroVector, CropMin=FVector::ZeroVector, CropMax=FVector::ZeroVector;
    float Units=100, Intensity=1, Opacity=1, Scale=1;
    uint32 Limit=5000000;
    EAbuM53Backend Backend=EAbuM53Backend::Auto;
    bool Crop=false;
    FMatrix LocalToWorld() const { return FScaleMatrix(FVector(Units))*FTranslationMatrix(Origin*Units)*SourceBasis*Transform.ToMatrixWithScale(); }
};
struct FM53ViewData
{
    const FSceneViewFamily* Family=nullptr;
    FVector Origin=FVector::ZeroVector;
};
// Unreal copies a view family when creating the renderer. This public extension
// payload travels with that copy and owns the immutable game-thread snapshot.
struct FM53FamilyData : public ISceneViewFamilyExtentionData
{
    inline static const TCHAR* GSubclassIdentifier=TEXT("AbuM53.FamilyData");
    TArray<FM53Snapshot> Items;
    virtual const TCHAR* GetSubclassIdentifier() const override { return GSubclassIdentifier; }
};
BEGIN_SHADER_PARAMETER_STRUCT(FM53DrawPass, )
    SHADER_PARAMETER_STRUCT_INCLUDE(FAbuM53DrawVS::FParameters, VS)
    SHADER_PARAMETER_STRUCT_INCLUDE(FAbuM53DrawPS::FParameters, PS)
    RENDER_TARGET_BINDING_SLOTS()
END_SHADER_PARAMETER_STRUCT()
BEGIN_SHADER_PARAMETER_STRUCT(FM53SoftwarePass, )
    SHADER_PARAMETER_STRUCT_INCLUDE(FAbuM53SoftwarePS::FParameters, PS)
    RENDER_TARGET_BINDING_SLOTS()
END_SHADER_PARAMETER_STRUCT()

class FM53ViewExtension : public FSceneViewExtensionBase
{
    TMap<const void*,FM53ViewData> Views;
    FAbuM53SourceCache SourceCache;
    FAbuM53SourceCacheStats LastSourceStats;
    uint64 Frame=0;
    bool WarnedBudget=false;
    bool WarnedSoftwareBudget=false;
    bool WarnedSoftwareCamera=false;
    void RecordSourceCacheStats()
    {
        const auto Stats=SourceCache.GetStats();
        CSV_CUSTOM_STAT(AbuM53,SourceUploadCount,int32(Stats.UploadCount-LastSourceStats.UploadCount),ECsvCustomStatOp::Accumulate);
        CSV_CUSTOM_STAT(AbuM53,SourceUploadMiB,float(Stats.UploadBytes-LastSourceStats.UploadBytes)/(1024.f*1024.f),ECsvCustomStatOp::Accumulate);
        CSV_CUSTOM_STAT(AbuM53,SourceCacheHits,int32(Stats.CacheHits-LastSourceStats.CacheHits),ECsvCustomStatOp::Accumulate);
        CSV_CUSTOM_STAT(AbuM53,SourcePendingReuses,int32(Stats.PendingReuses-LastSourceStats.PendingReuses),ECsvCustomStatOp::Accumulate);
        CSV_CUSTOM_STAT(AbuM53,SourceCacheEvictions,int32(Stats.Evictions-LastSourceStats.Evictions),ECsvCustomStatOp::Accumulate);
        CSV_CUSTOM_STAT(AbuM53,SourceUncachedUploads,int32(Stats.UncachedUploads-LastSourceStats.UncachedUploads),ECsvCustomStatOp::Accumulate);
        CSV_CUSTOM_STAT(AbuM53,SourceCacheResidentMiB,float(Stats.ResidentBytes)/(1024.f*1024.f),ECsvCustomStatOp::Set);
        CSV_CUSTOM_STAT(AbuM53,SourceCacheReservedMiB,float(Stats.ReservedBytes)/(1024.f*1024.f),ECsvCustomStatOp::Set);
        CSV_CUSTOM_STAT(AbuM53,SourceCacheEntries,Stats.Entries,ECsvCustomStatOp::Set);
        LastSourceStats=Stats;
    }
public:
    FM53ViewExtension(const FAutoRegister& A):FSceneViewExtensionBase(A){}
    virtual void SetupViewFamily(FSceneViewFamily&) override {}
    virtual void SetupView(FSceneViewFamily&,FSceneView&) override {}
    virtual void BeginRenderViewFamily(FSceneViewFamily& Family) override
    {
        TArray<FM53Snapshot> Items;
        if(Family.Scene && Family.EngineShowFlags.Rendering)
        for(auto Weak:UAbuM53Component::GetRegisteredComponents())
        {
            auto* C=Weak.Get();
            if(!C||C->GetWorld()!=Family.Scene->GetWorld()||!C->IsVisible()||(C->GetOwner()&&C->GetOwner()->IsHidden()))continue;
            auto Points=C->GetRenderPoints();if(!Points||Points->IsEmpty())continue;
            FM53Snapshot S;S.Id=C->GetUniqueID();S.Points=Points;S.Transform=C->GetComponentTransform();S.Origin=C->GetSourceOrigin();
            S.SourceBasis=C->GetSourceAxisMatrix();
            S.Units=C->UnitsToCentimeters;S.Intensity=C->Intensity;S.Opacity=C->OpacityMultiplier;S.Scale=C->SplatScale;
            S.Limit=FMath::Max(1,C->MaxVisibleSplats);S.Crop=C->bEnableCrop;S.CropMin=C->CropMin-S.Origin;S.CropMax=C->CropMax-S.Origin;S.Backend=C->Backend;
            Items.Add(MoveTemp(S));
        }
        Family.GetOrCreateExtentionData<FM53FamilyData>()->Items=MoveTemp(Items);
    }
    virtual void PreRenderViewFamily_RenderThread(FRDGBuilder&,FSceneViewFamily& Family) override
    {
        ++Frame;
        SourceCache.BeginFrame(Frame,uint64(FMath::Clamp(CVarM53SourceCache.GetValueOnRenderThread(),0,8192))*1024*1024);
        RecordSourceCacheStats();
    }
    virtual void PreRenderView_RenderThread(FRDGBuilder&,FSceneView& V) override
    {
        FM53ViewData D;D.Family=V.Family;D.Origin=V.ViewMatrices.GetViewOrigin();
        Views.Add(&V,D);
    }
    virtual void PostRenderViewFamily_RenderThread(FRDGBuilder&,FSceneViewFamily& F) override
    {
        for(auto It=Views.CreateIterator();It;++It)if(It.Value().Family==&F)It.RemoveCurrent();
    }
    void Render(FPostOpaqueRenderParameters& R)
    {
        if(!CVarM53Enable.GetValueOnRenderThread()||!R.GraphBuilder||!R.ColorTexture||!R.DepthTexture)return;
        auto* V=Views.Find(R.Uid);if(!V)return;
        const auto* FamilyData=V->Family->GetExtentionData<FM53FamilyData>();if(!FamilyData)return;
        const auto* Items=&FamilyData->Items;if(Items->IsEmpty())return;
        uint64 Requested=0;const uint32 Budget=FMath::Clamp(CVarM53Max.GetValueOnRenderThread(),1,20000000);
        for(const auto& S:*Items)Requested+=FMath::Min<uint32>(S.Points->Num(),S.Limit);
        if(Requested>Budget&&!WarnedBudget){UE_LOG(LogAbuM53Render,Warning,TEXT("Selected %llu splats exceed view budget %u; increase r.AbuM53.MaxSplats for full fidelity."),Requested,Budget);WarnedBudget=true;}
        const uint32 Total=static_cast<uint32>(FMath::Min<uint64>(Requested,Budget));if(!Total)return;
        CSV_CUSTOM_STAT(AbuM53,RenderedViews,1,ECsvCustomStatOp::Accumulate);
        CSV_CUSTOM_STAT(AbuM53,SelectedSplats,static_cast<int32>(Total),ECsvCustomStatOp::Set);
        int32 Backend=CVarM53Backend.GetValueOnRenderThread();
        if(!Backend)for(const auto& S:*Items)Backend=FMath::Max(Backend,static_cast<int32>(S.Backend));
        if(Backend==3)
        {
            if(Total>50000&&!WarnedSoftwareBudget){UE_LOG(LogAbuM53Render,Warning,TEXT("CPU software preview is capped at 50,000 splats; %u selected splats will not all be drawn."),Total);WarnedSoftwareBudget=true;}
            RenderSoftware(R,*V,*Items);return;
        }
        FRDGBuilder& Graph=*R.GraphBuilder;
        RDG_EVENT_SCOPE_STAT(Graph,AbuM53,"AbuM53 %u splats",Total);
        auto* ShaderMap=GetGlobalShaderMap(GMaxRHIFeatureLevel);
        auto Projected=Graph.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(16,Total*3),TEXT("AbuM53.Projected"));
        auto KeysA=Graph.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(8,Total),TEXT("AbuM53.KeysA"));
        auto KeysB=Graph.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(8,Total),TEXT("AbuM53.KeysB"));
        uint32 Offset=0;
        TArray<TPair<float,uint32>> CpuKeys;if(Backend==2)CpuKeys.Reserve(Total);
        for(const auto& S:*Items)
        {
            uint32 Count=FMath::Min<uint32>(FMath::Min<uint32>(S.Points->Num(),S.Limit),Total-Offset);if(!Count)break;
            FRDGBufferRef Source=SourceCache.Acquire(Graph,S.Id,S.Points);
            auto* P=Graph.AllocParameters<FAbuM53ProjectCS::FParameters>();
            const FMatrix World=S.LocalToWorld();const FMatrix Clip=World*R.ViewMatrix*R.ProjMatrix;
            P->PointCount=Count;P->OutputOffset=Offset;P->LocalToClip=FMatrix44f(Clip);P->LocalToView=FMatrix44f(World*R.ViewMatrix);
            P->CameraLocal=FVector3f(FVector(World.Inverse().TransformPosition(V->Origin)));P->ViewSize=FVector2f(R.ViewportRect.Width(),R.ViewportRect.Height());
            P->Intensity=S.Intensity;P->OpacityMultiplier=S.Opacity;P->SplatScale=S.Scale;
            P->FilterVariance=FMath::Max(0.0f,CVarM53Filter.GetValueOnRenderThread());P->View=TUniformBufferRef<FViewUniformShaderParameters>(R.ViewUniformBuffer);
            P->CropEnabled=S.Crop;P->CropMin=FVector3f(S.CropMin);P->CropMax=FVector3f(S.CropMax);
            P->SourcePoints=Graph.CreateSRV(Source);P->Projected=Graph.CreateUAV(Projected);P->KeysOut=Graph.CreateUAV(KeysA);
            const uint32 ProjectGroups=FMath::DivideAndRoundUp(Count,256u);
            FComputeShaderUtils::AddPass(Graph,RDG_EVENT_NAME("AbuM53.Project"),TShaderMapRef<FAbuM53ProjectCS>(ShaderMap),P,FIntVector(FMath::Min(ProjectGroups,65535u),FMath::DivideAndRoundUp(ProjectGroups,65535u),1));
            if(Backend==2)for(uint32 i=0;i<Count;i++)
            {
                const auto& Q=(*S.Points)[i].PositionOpacity;
                float Depth=float((World*R.ViewMatrix).TransformFVector4(FVector4(Q.X,Q.Y,Q.Z,1)).Z);
                CpuKeys.Emplace(Depth,Offset+i);
            }
            Offset+=Count;
        }
        RecordSourceCacheStats();
        FRDGBufferRef Sorted=KeysA;
        if(Backend==2)
        {
            CpuKeys.StableSort([](const auto&A,const auto&B){return A.Key<B.Key;});
            TArray<FUintVector2> K;K.Reserve(Total);for(const auto& I:CpuKeys)K.Add(FUintVector2(0,I.Value));
            Sorted=CreateStructuredBuffer(Graph,TEXT("AbuM53.CPUSorted"),K);
        }
        else
        {
            uint32 Groups=FMath::DivideAndRoundUp(Total,256u);
            auto Histogram=Graph.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(4,Groups*16),TEXT("AbuM53.Histogram"));
            FRDGBufferRef In=KeysA,Out=KeysB;
            for(uint32 Shift=0;Shift<32;Shift+=4)
            {
                auto* H=Graph.AllocParameters<FAbuM53HistogramCS::FParameters>();H->TotalCount=Total;H->GroupCount=Groups;H->DigitShift=Shift;H->KeysIn=Graph.CreateSRV(In);H->Histogram=Graph.CreateUAV(Histogram);
                FComputeShaderUtils::AddPass(Graph,RDG_EVENT_NAME("AbuM53.RadixHistogram"),TShaderMapRef<FAbuM53HistogramCS>(ShaderMap),H,FIntVector(FMath::Min(Groups,65535u),FMath::DivideAndRoundUp(Groups,65535u),1));
                auto Offsets=AddAbuM53ExclusiveScan(Graph,Histogram,Groups*16);
                auto* C=Graph.AllocParameters<FAbuM53ScatterCS::FParameters>();C->TotalCount=Total;C->GroupCount=Groups;C->DigitShift=Shift;C->KeysIn=Graph.CreateSRV(In);C->OffsetsIn=Graph.CreateSRV(Offsets);C->KeysOut=Graph.CreateUAV(Out);
                FComputeShaderUtils::AddPass(Graph,RDG_EVENT_NAME("AbuM53.RadixScatter"),TShaderMapRef<FAbuM53ScatterCS>(ShaderMap),C,FIntVector(FMath::Min(Groups,65535u),FMath::DivideAndRoundUp(Groups,65535u),1));Swap(In,Out);
            }
            Sorted=In;
        }
        FRDGBufferRef Overflow=nullptr;
        if(CVarM53Tiles.GetValueOnRenderThread())Overflow=AddAbuM53TilePass(Graph,Projected,Sorted,Total,R.DepthTexture,R.ColorTexture,R.ViewportRect,FMath::Max(0.0f,CVarM53Cutoff.GetValueOnRenderThread()));
        else {const uint32 One=1;Overflow=CreateStructuredBuffer(Graph,TEXT("AbuM53.QuadOnly"),4,1,&One,4);}
        auto* P=Graph.AllocParameters<FM53DrawPass>();P->VS.TotalCount=Total;P->VS.ViewSize=FVector2f(R.ViewportRect.Width(),R.ViewportRect.Height());P->VS.ProjectedIn=Graph.CreateSRV(Projected);P->VS.SortedKeys=Graph.CreateSRV(Sorted);P->VS.TileOverflow=Graph.CreateSRV(Overflow);
        P->PS.SceneDepth=R.DepthTexture;P->PS.AlphaCutoff=FMath::Max(0.0f,CVarM53Cutoff.GetValueOnRenderThread());P->RenderTargets[0]=FRenderTargetBinding(R.ColorTexture,ERenderTargetLoadAction::ELoad);
        TShaderMapRef<FAbuM53DrawVS> VS(ShaderMap);TShaderMapRef<FAbuM53DrawPS> PS(ShaderMap);const FIntRect Rect=R.ViewportRect;
        Graph.AddPass(RDG_EVENT_NAME("AbuM53.SortedSplats"),P,ERDGPassFlags::Raster,[P,VS,PS,Rect,Total](FRHICommandList& Cmd)
        {
            Cmd.SetViewport(Rect.Min.X,Rect.Min.Y,0,Rect.Max.X,Rect.Max.Y,1);
            FGraphicsPipelineStateInitializer State;Cmd.ApplyCachedRenderTargets(State);
            State.BlendState=TStaticBlendState<CW_RGBA,BO_Add,BF_One,BF_InverseSourceAlpha,BO_Add,BF_One,BF_InverseSourceAlpha>::GetRHI();
            State.RasterizerState=TStaticRasterizerState<FM_Solid,CM_None>::GetRHI();State.DepthStencilState=TStaticDepthStencilState<false,CF_Always>::GetRHI();State.PrimitiveType=PT_TriangleList;
            State.BoundShaderState.VertexDeclarationRHI=GEmptyVertexDeclaration.VertexDeclarationRHI;State.BoundShaderState.VertexShaderRHI=VS.GetVertexShader();State.BoundShaderState.PixelShaderRHI=PS.GetPixelShader();
            SetGraphicsPipelineState(Cmd,State,0);SetShaderParameters(Cmd,VS,VS.GetVertexShader(),P->VS);SetShaderParameters(Cmd,PS,PS.GetPixelShader(),P->PS);Cmd.DrawPrimitive(0,2,Total);
        });
    }
    void RenderSoftware(FPostOpaqueRenderParameters& R,const FM53ViewData& V,const TArray<FM53Snapshot>& Items)
    {
        if(R.ProjMatrix.M[3][3]!=0)
        {
            if(!WarnedSoftwareCamera){UE_LOG(LogAbuM53Render,Warning,TEXT("CPU software preview requires a perspective camera. GPU rendering supports orthographic views."));WarnedSoftwareCamera=true;}
            return;
        }
        abum53::Cloud Cloud;Cloud.shDegree=0;
        const uint32 Limit=FMath::Min(50000,FMath::Clamp(CVarM53Max.GetValueOnRenderThread(),1,20000000));
        for(const auto& S:Items)
        {
            const FMatrix World=S.LocalToWorld();
            const FVector CameraLocal=World.Inverse().TransformPosition(V.Origin);
            for(int32 i=0;i<FMath::Min<int32>(S.Limit,S.Points->Num())&&Cloud.splats.size()<Limit;i++)
            {
                const auto& P=(*S.Points)[i];const FVector Local(P.PositionOpacity.X,P.PositionOpacity.Y,P.PositionOpacity.Z);
                if(S.Crop&&(Local.X<S.CropMin.X||Local.Y<S.CropMin.Y||Local.Z<S.CropMin.Z||Local.X>S.CropMax.X||Local.Y>S.CropMax.Y||Local.Z>S.CropMax.Z))continue;
                abum53::Gaussian G;FVector X=World.TransformPosition(Local);G.position[0]=X.X;G.position[1]=X.Y;G.position[2]=X.Z;
                M53TransformShape(World,P,S.Scale,G);
                G.opacity=FMath::Clamp(P.PositionOpacity.W*S.Opacity,0.0f,0.999f);
                G.antialiased=P.Metadata.Z>0.5f;
                const FVector Direction=(Local-CameraLocal).GetSafeNormal();
                float Color[3];abum53::EvaluateSHInto(reinterpret_cast<const float*>(P.SH),(uint32)P.ScaleDegree.W,Direction.X,Direction.Y,Direction.Z,Color);
                for(int k=0;k<3;k++){double C=FMath::Clamp(double(Color[k]),0.0,64.0);C=(C<=0.04045?C/12.92:FMath::Pow((C+0.055)/1.055,2.4))*S.Intensity;G.sh[k]=(C-0.5)/0.28209479177387814;}
                Cloud.splats.push_back(G);
            }
        }
        abum53::Camera C;C.width=FMath::Min(1280,R.ViewportRect.Width());C.height=FMath::Max(1u,C.width*R.ViewportRect.Height()/R.ViewportRect.Width());
        C.focalX=R.ProjMatrix.M[0][0]*C.width*0.5;C.focalY=R.ProjMatrix.M[1][1]*C.height*0.5;C.centerX=C.width*0.5;C.centerY=C.height*0.5;C.nearPlane=0.01;
        const FMatrix Inv=R.ViewMatrix.Inverse();const FVector Right=Inv.TransformVector(FVector(1,0,0)),Up=Inv.TransformVector(FVector(0,1,0)),Forward=Inv.TransformVector(FVector(0,0,1));
        for(int k=0;k<3;k++){C.position[k]=V.Origin[k];C.right[k]=Right[k];C.up[k]=Up[k];C.forward[k]=Forward[k];}
        abum53::RenderOptions O;O.maxSplats=50000;O.filterVariance=FMath::Max(0.0f,CVarM53Filter.GetValueOnRenderThread());O.alphaCutoff=FMath::Max(0.0f,CVarM53Cutoff.GetValueOnRenderThread());abum53::RenderResult Result;std::string Error;
        if(!abum53::RenderCPU(Cloud,C,O,Result,Error)){UE_LOG(LogAbuM53Render,Warning,TEXT("CPU preview: %s"),UTF8_TO_TCHAR(Error.c_str()));return;}
        FRDGBuilder& Graph=*R.GraphBuilder;auto Pixels=CreateStructuredBuffer(Graph,TEXT("AbuM53.SoftwarePixels"),16,C.width*C.height,Result.rgba.data(),Result.rgba.size()*4);
        auto* P=Graph.AllocParameters<FM53SoftwarePass>();P->PS.ViewMin=FVector2f(R.ViewportRect.Min);P->PS.ViewSize=FVector2f(R.ViewportRect.Size());P->PS.SoftwareSize=FVector2f(C.width,C.height);P->PS.View=TUniformBufferRef<FViewUniformShaderParameters>(R.ViewUniformBuffer);P->PS.SoftwarePixels=Graph.CreateSRV(Pixels);P->RenderTargets[0]=FRenderTargetBinding(R.ColorTexture,ERenderTargetLoadAction::ELoad);
        auto* Map=GetGlobalShaderMap(GMaxRHIFeatureLevel);TShaderMapRef<FAbuM53SoftwareVS> VS(Map);TShaderMapRef<FAbuM53SoftwarePS> PS(Map);FIntRect Rect=R.ViewportRect;
        Graph.AddPass(RDG_EVENT_NAME("AbuM53.SoftwareComposite"),P,ERDGPassFlags::Raster,[P,VS,PS,Rect](FRHICommandList& Cmd)
        {
            Cmd.SetViewport(Rect.Min.X,Rect.Min.Y,0,Rect.Max.X,Rect.Max.Y,1);FGraphicsPipelineStateInitializer S;Cmd.ApplyCachedRenderTargets(S);
            S.BlendState=TStaticBlendState<CW_RGBA,BO_Add,BF_One,BF_InverseSourceAlpha>::GetRHI();S.RasterizerState=TStaticRasterizerState<FM_Solid,CM_None>::GetRHI();S.DepthStencilState=TStaticDepthStencilState<false,CF_Always>::GetRHI();S.PrimitiveType=PT_TriangleList;
            S.BoundShaderState.VertexDeclarationRHI=GEmptyVertexDeclaration.VertexDeclarationRHI;S.BoundShaderState.VertexShaderRHI=VS.GetVertexShader();S.BoundShaderState.PixelShaderRHI=PS.GetPixelShader();SetGraphicsPipelineState(Cmd,S,0);SetShaderParameters(Cmd,PS,PS.GetPixelShader(),P->PS);Cmd.DrawPrimitive(0,1,1);
        });
    }
};

class FAbuM53RenderModule final:public IModuleInterface
{
    TSharedPtr<FM53ViewExtension,ESPMode::ThreadSafe> Extension;
    FDelegateHandle EngineHandle,RenderHandle;
public:
    void StartRenderer()
    {
        if(IsRunningCommandlet()&&!IsAllowCommandletRendering())return;
        Extension=FSceneViewExtensions::NewExtension<FM53ViewExtension>();
        auto& Renderer=FModuleManager::LoadModuleChecked<IRendererModule>(TEXT("Renderer"));
        RenderHandle=Renderer.RegisterPostOpaqueRenderDelegate(FPostOpaqueRenderDelegate::CreateSP(Extension.ToSharedRef(),&FM53ViewExtension::Render));
    }
    virtual void StartupModule() override
    {
        const auto Plugin=IPluginManager::Get().FindPlugin(TEXT("AbuM53"));
        if(Plugin)AddShaderSourceDirectoryMapping(TEXT("/Plugin/AbuM53"),FPaths::Combine(Plugin->GetBaseDir(),TEXT("Shaders")));
        EngineHandle=FCoreDelegates::GetOnPostEngineInit().AddRaw(this,&FAbuM53RenderModule::StartRenderer);
    }
    virtual void ShutdownModule() override
    {
        FCoreDelegates::GetOnPostEngineInit().Remove(EngineHandle);
        if(auto* R=FModuleManager::GetModulePtr<IRendererModule>(TEXT("Renderer")))R->RemovePostOpaqueRenderDelegate(RenderHandle);
        FlushRenderingCommands();Extension.Reset();
    }
};
IMPLEMENT_MODULE(FAbuM53RenderModule,AbuM53Render)
