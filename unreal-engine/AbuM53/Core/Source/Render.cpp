// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53/Core.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <fstream>
#include <numeric>
#include <stdexcept>
#include <thread>

namespace abum53 { namespace {
constexpr uint32_t TileEdge=16;
struct Projected {
    double x,y,z,key,a,b,c;
    float opacity;
    std::array<float,3> color;
    int minX,minY,maxX,maxY;
    uint64_t id;
};
double Dot(const double* a,const double* b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
void Check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
void Covariance(const Gaussian& g,double cov[3][3]){
    const double x=g.rotation[0],y=g.rotation[1],z=g.rotation[2],w=g.rotation[3];
    const double r[3][3]={{1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)},
        {2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)},
        {2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)}};
    for(int i=0;i<3;++i)for(int j=0;j<3;++j){cov[i][j]=0;for(int k=0;k<3;++k)cov[i][j]+=r[i][k]*r[j][k]*double(g.scale[k])*g.scale[k];}
}
} // anonymous
bool RenderCPU(const Cloud& cloud,const Camera& camera,const RenderOptions& options,RenderResult& output,std::string& error){
    try{
        error.clear();Check(camera.width>0&&camera.height>0&&camera.width<=8192&&camera.height<=8192,"CPU image dimensions outside [1,8192]");
        Check(uint64_t(camera.width)*camera.height<=16777216,"CPU image exceeds 16M pixel budget");
        Check(cloud.shDegree<=3,"Unsupported SH degree");Check(cloud.splats.size()<=options.maxSplats,"CPU selected-splat budget exceeded");
        Check(std::isfinite(camera.focalX)&&std::isfinite(camera.focalY)&&camera.focalX>0&&camera.focalY>0&&std::isfinite(camera.nearPlane)&&camera.nearPlane>0,"Invalid camera projection");
        Check(std::isfinite(camera.centerX)&&std::isfinite(camera.centerY),"Invalid camera center");
        for(double v:camera.position)Check(std::isfinite(v),"Nonfinite camera position");
        const double* axes[3]={camera.right,camera.up,camera.forward};
        for(int i=0;i<3;++i)for(int j=0;j<3;++j)Check(std::isfinite(Dot(axes[i],axes[j]))&&std::abs(Dot(axes[i],axes[j])-(i==j?1:0))<1e-5,"Camera basis must be orthonormal");
        Check(options.filterVariance>=0&&std::isfinite(options.filterVariance)&&options.alphaCutoff>=0&&options.alphaCutoff<1&&options.transmittanceCutoff>=0&&options.transmittanceCutoff<1,"Invalid CPU filter/cutoff settings");
        for(float v:options.background)Check(std::isfinite(v)&&v>=0,"Invalid CPU background");
        std::vector<Projected> projected;projected.reserve(cloud.splats.size());uint64_t estimatedContributions=0;
        for(size_t n=0;n<cloud.splats.size();++n){const auto& g=cloud.splats[n];
            double qnorm=0;for(float q:g.rotation){Check(std::isfinite(q),"Nonfinite Gaussian rotation");qnorm+=double(q)*q;}Check(std::abs(qnorm-1)<1e-3,"Gaussian rotation must be normalized");
            for(uint32_t i=0;i<3*(cloud.shDegree+1)*(cloud.shDegree+1);++i)Check(std::isfinite(g.sh[i]),"Nonfinite SH coefficient");
            double delta[3];for(int i=0;i<3;++i){delta[i]=g.position[i]+cloud.origin[i]-camera.position[i];Check(std::isfinite(delta[i])&&std::isfinite(g.scale[i])&&g.scale[i]>0,"Invalid Gaussian geometry");}
            const double vx=Dot(delta,camera.right),vy=Dot(delta,camera.up),vz=Dot(delta,camera.forward);
            Check(std::isfinite(g.opacity)&&g.opacity>=0&&g.opacity<=1,"Invalid Gaussian opacity");
            if(g.opacity<options.alphaCutoff||vz<=0)continue;
            double sourceCov[3][3],viewCov[3][3]{};Covariance(g,sourceCov);
            for(int i=0;i<3;++i)for(int j=0;j<3;++j)for(int a=0;a<3;++a)for(int b=0;b<3;++b)viewCov[i][j]+=axes[i][a]*sourceCov[a][b]*axes[j][b];
            const double extent=3*std::sqrt(std::max(0.0,viewCov[2][2]));
            if(vz+extent<=camera.nearPlane)continue;
            Check(vz-extent>camera.nearPlane,"CPU reference cannot render a Gaussian intersecting the near plane; move camera or reduce scale");
            const double jac[2][3]={{camera.focalX/vz,0,-camera.focalX*vx/(vz*vz)},{0,-camera.focalY/vz,camera.focalY*vy/(vz*vz)}};
            double c2[2][2]{};for(int i=0;i<2;++i)for(int j=0;j<2;++j)for(int a=0;a<3;++a)for(int b=0;b<3;++b)c2[i][j]+=jac[i][a]*viewCov[a][b]*jac[j][b];
            const double oldDet=c2[0][0]*c2[1][1]-c2[0][1]*c2[1][0];c2[0][0]+=options.filterVariance;c2[1][1]+=options.filterVariance;
            const double det=c2[0][0]*c2[1][1]-c2[0][1]*c2[1][0];Check(std::isfinite(det)&&det>1e-20,"Degenerate projected Gaussian");
            Projected p{};p.x=camera.centerX+camera.focalX*vx/vz;p.y=camera.centerY-camera.focalY*vy/vz;p.z=vz;p.key=options.cameraDistanceSort?Dot(delta,delta):vz;
            p.a=c2[1][1]/det;p.b=-c2[0][1]/det;p.c=c2[0][0]/det;p.opacity=g.opacity;
            if(options.opacityCompensation||cloud.antialiased||g.antialiased)p.opacity*=float(std::sqrt(std::max(0.0,oldDet)/det));
            p.color=EvaluateSH(g.sh,cloud.shDegree,delta[0],delta[1],delta[2]);p.id=n;
            const double rx=3*std::sqrt(c2[0][0]),ry=3*std::sqrt(c2[1][1]);
            Check(std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(rx)&&std::isfinite(ry),"Nonfinite projected Gaussian");
            if(p.x+rx<0||p.y+ry<0||p.x-rx>=camera.width||p.y-ry>=camera.height)continue;
            p.minX=int(std::max(0.0,std::floor(p.x-rx)));p.minY=int(std::max(0.0,std::floor(p.y-ry)));
            p.maxX=int(std::min(double(camera.width)-1,std::ceil(p.x+rx)));p.maxY=int(std::min(double(camera.height)-1,std::ceil(p.y+ry)));
            const uint64_t area=uint64_t(p.maxX-p.minX+1)*uint64_t(p.maxY-p.minY+1);
            Check(area<=options.maxPixelContributions&&estimatedContributions<=options.maxPixelContributions-area,"CPU pixel contribution budget exceeded");estimatedContributions+=area;projected.push_back(p);
        }
        std::stable_sort(projected.begin(),projected.end(),[](const Projected& a,const Projected& b){return a.key<b.key||(a.key==b.key&&a.id<b.id);});
        const uint32_t tilesX=(camera.width+TileEdge-1)/TileEdge,tilesY=(camera.height+TileEdge-1)/TileEdge;
        std::vector<std::vector<uint32_t>> bins(size_t(tilesX)*tilesY);uint64_t references=0;
        for(uint32_t n=0;n<projected.size();++n){const auto& p=projected[n];for(int ty=p.minY/int(TileEdge);ty<=p.maxY/int(TileEdge);++ty)for(int tx=p.minX/int(TileEdge);tx<=p.maxX/int(TileEdge);++tx){Check(++references<=8000000,"CPU tile reference budget exceeded");bins[size_t(ty)*tilesX+tx].push_back(n);}}
        RenderResult result;result.width=camera.width;result.height=camera.height;result.projectedSplats=projected.size();result.rgba.resize(size_t(camera.width)*camera.height*4);
        std::atomic<uint32_t> next{0};std::atomic<uint64_t> contributions{0};
        auto work=[&]{uint64_t localCount=0;for(;;){const uint32_t tile=next.fetch_add(1,std::memory_order_relaxed);if(tile>=bins.size())break;
            const uint32_t x0=(tile%tilesX)*TileEdge,y0=(tile/tilesX)*TileEdge;
            for(uint32_t y=y0;y<std::min(camera.height,y0+TileEdge);++y)for(uint32_t x=x0;x<std::min(camera.width,x0+TileEdge);++x){double color[3]={0,0,0},trans=1;
                for(uint32_t id:bins[tile]){const auto& p=projected[id];if(int(x)<p.minX||int(x)>p.maxX||int(y)<p.minY||int(y)>p.maxY)continue;
                    const double dx=x+.5-p.x,dy=y+.5-p.y,quadratic=p.a*dx*dx+2*p.b*dx*dy+p.c*dy*dy;
                    if(quadratic>9)continue;const double alpha=std::min(.999,double(p.opacity)*std::exp(-.5*quadratic));if(alpha<options.alphaCutoff)continue;
                    for(int c=0;c<3;++c)color[c]+=trans*alpha*p.color[c];trans*=1-alpha;++localCount;if(trans<=options.transmittanceCutoff)break;
                }
                const size_t pixel=(size_t(y)*camera.width+x)*4;for(int c=0;c<3;++c)result.rgba[pixel+c]=float(color[c]+trans*options.background[c]);result.rgba[pixel+3]=float(1-trans);
            }
        }contributions.fetch_add(localCount,std::memory_order_relaxed);};
        const uint32_t threads=std::max(1u,std::min(32u,options.workerCount?options.workerCount:std::thread::hardware_concurrency()));
        std::vector<std::thread> workers;workers.reserve(threads-1);
        try{for(uint32_t i=1;i<threads;++i)workers.emplace_back(work);}catch(...){for(auto& thread:workers)thread.join();throw;}
        work();for(auto& thread:workers)thread.join();result.pixelContributions=contributions.load();output=std::move(result);return true;
    }catch(const std::exception& e){error=e.what();return false;}catch(...){error="Unknown CPU rendering error";return false;}
}
bool WritePPM(const std::filesystem::path& path,const RenderResult& image,std::string& error){
    try{Check(image.width>0&&image.height>0&&image.rgba.size()==size_t(image.width)*image.height*4,"Invalid image buffer");std::ofstream out(path,std::ios::binary);Check(bool(out),"Cannot create PPM image");out<<"P6\n"<<image.width<<" "<<image.height<<"\n255\n";
        for(size_t i=0;i<image.rgba.size();i+=4)for(int c=0;c<3;++c){const float v=image.rgba[i+c];Check(std::isfinite(v),"Nonfinite image value");const auto b=static_cast<unsigned char>(std::lround(std::max(0.f,std::min(1.f,v))*255.f));out.put(static_cast<char>(b));}
        Check(bool(out),"Cannot finish PPM image");error.clear();return true;
    }catch(const std::exception& e){error=e.what();return false;}
}
} // namespace abum53
