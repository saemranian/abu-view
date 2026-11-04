// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53/Core.h"
#include "AbuM53/Codecs.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>

static int checks=0;
static void Check(bool v,const char* description){++checks;if(!v)throw std::runtime_error(description);}
static bool Near(double a,double b,double tolerance=1e-5){return std::abs(a-b)<=tolerance;}
static void Text(const std::filesystem::path& p,const std::string& s){std::ofstream o(p,std::ios::binary);o<<s;}
template<class T> static void Num(std::ostream& out,T value,bool big=false){unsigned char b[sizeof(T)];std::memcpy(b,&value,sizeof(T));uint16_t h=1;if((*reinterpret_cast<unsigned char*>(&h)==1)==big)std::reverse(b,b+sizeof(T));out.write(reinterpret_cast<const char*>(b),sizeof(T));}
static std::string Header(const std::string& format,int degree=0){
    std::ostringstream h;h<<"ply\nformat "<<format<<" 1.0\nelement vertex 1\n";
    h<<"property double z\nproperty float opacity\nproperty float x\nproperty float f_dc_2\nproperty float scale_2\nproperty float rot_0\nproperty float y\nproperty float f_dc_0\nproperty float scale_0\nproperty float rot_3\nproperty float f_dc_1\nproperty float scale_1\nproperty float rot_2\nproperty float rot_1\n";
    for(int i=0;i<3*((degree+1)*(degree+1)-1);++i)h<<"property float f_rest_"<<i<<"\n";h<<"end_header\n";return h.str();
}
int main(int argc,char** argv){try{
    const auto base=argc>1?std::filesystem::u8path(argv[1]):std::filesystem::temp_directory_path()/"m53-tests";
    const auto dir=base/std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());std::filesystem::create_directories(dir);
    std::string error;abum53::Cloud cloud;
    Text(dir/"ascii.ply",Header("ascii")+"5 0 1 0 -2 1 2 0 -2 0 0 -2 0 0\n");
    Check(abum53::LoadFile(dir/"ascii.ply",cloud,error),error.c_str());Check(cloud.splats.size()==1,"ASCII count");Check(Near(cloud.splats[0].position[0],1)&&Near(cloud.splats[0].position[1],2)&&Near(cloud.splats[0].position[2],5),"Named-property mapping");
    Check(Near(cloud.splats[0].opacity,.5)&&Near(cloud.splats[0].scale[0],std::exp(-2.0)),"Parameter activation");Check(Near(cloud.splats[0].rotation[3],1),"Quaternion WXYZ->XYZW");
    for(bool big:{false,true}){const auto p=dir/(big?"be.ply":"le.ply");std::ofstream out(p,std::ios::binary);out<<Header(big?"binary_big_endian":"binary_little_endian",3);Num(out,5.1234567890123,big);const float values[]={0,1,0,-2,1,2,0,-2,0,0,-2,0,0};for(float v:values)Num(out,v,big);for(int i=0;i<45;++i)Num(out,float(i),big);out.close();
        Check(abum53::LoadFile(p,cloud,error),error.c_str());Check(cloud.shDegree==3,"SH3 detection");Check(Near(cloud.splats[0].position[2],5.1234567890123,1e-13),"Double position preserved");Check(cloud.splats[0].sh[3]==0&&cloud.splats[0].sh[4]==15&&cloud.splats[0].sh[5]==30&&cloud.splats[0].sh[47]==44,"Channel-major SH mapped to coefficient-major");}
    // Cross chunk boundaries, exercise mixed widths, surrounding elements and list fallback.
    for(bool big:{false,true})for(bool lists:{false,true}){
        const auto p=dir/((big?std::string("chunk_be"):std::string("chunk_le"))+(lists?"_lists.ply":".ply"));
        auto h=Header(big?"binary_big_endian":"binary_little_endian",3);
        h.replace(h.find("vertex 1"),8,"vertex 8201");
        h.insert(h.find("element vertex"),"element prefix 1\nproperty uchar tag\n");
        h.insert(h.find("end_header"),lists?"property list uchar int neighbors\n":"property uchar unused8\nproperty short unused16\nproperty uint unused32\n");
        h.insert(h.find("end_header"),"element face 1\nproperty list uchar int indices\n");
        std::ofstream out(p,std::ios::binary);out<<h;Num(out,uint8_t(42));
        for(int row=0;row<8201;++row){Num(out,5.1234567890123+row,big);for(float v:{0.f,float(row),0.f,-2.f,1.f,2.f,0.f,-2.f,0.f,0.f,-2.f,0.f,0.f})Num(out,v,big);
            for(int i=0;i<45;++i)Num(out,float(i),big);
            if(lists){Num(out,uint8_t(2));Num(out,int32_t(-7),big);Num(out,int32_t(9),big);}
            else{Num(out,uint8_t(123));Num(out,int16_t(-1234),big);Num(out,uint32_t(4000000000u),big);}}
        Num(out,uint8_t(3));for(int i:{0,1,2})Num(out,int32_t(i),big);out.close();
        Check(abum53::LoadFile(p,cloud,error),error.c_str());Check(cloud.splats.size()==8201,"Chunk/list vertex count");
        Check(cloud.splats[4096].position[0]==4096&&Near(cloud.splats.back().position[2],8205.1234567890123,1e-10)&&cloud.splats.back().sh[47]==44,"Chunk boundaries retain all attributes and double precision");
        int polls=0;abum53::LoadOptions cancelled;cancelled.shouldCancel=[&]{return ++polls>=4;};
        Check(!abum53::LoadFile(p,cloud,error,cancelled)&&error=="Import cancelled","Mid-import cooperative cancellation");
        Check(cloud.splats.size()==8201&&cloud.splats.back().id==8200,"Cancelled decode preserves published cloud");
        std::filesystem::resize_file(p,std::filesystem::file_size(p)-20);
        Check(!abum53::LoadFile(p,cloud,error),"Reject truncated binary row/list across chunks");
    }
    {auto h=Header("binary_little_endian");h.replace(h.find("vertex 1"),8,"vertex 10000000");Text(dir/"empty_large.ply",h);
        Check(!abum53::LoadFile(dir/"empty_large.ply",cloud,error)&&error=="Truncated binary PLY body","Reject impossible binary body before allocation");}
    Text(dir/"point.ply","ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n");
    const auto oldCount=cloud.splats.size();Check(!abum53::LoadFile(dir/"point.ply",cloud,error),"Reject point-only PLY");Check(cloud.splats.size()==oldCount,"Failed import preserves output");
    Text(dir/"truncated.ply",Header("ascii")+"1 2\n");Check(!abum53::LoadFile(dir/"truncated.ply",cloud,error),"Reject truncated ASCII");
    {auto h=Header("ascii");h.insert(h.find("element vertex"),"element empty_attack 8000000000\n");Text(dir/"propertyless.ply",h+"5 0 1 0 -2 1 2 0 -2 0 0 -2 0 0\n");Check(!abum53::LoadFile(dir/"propertyless.ply",cloud,error),"Reject nonempty PLY element without properties");Check(error=="Nonempty PLY element has no properties","Propertyless PLY rejected before body iteration");}
    Text(dir/"nan.ply",Header("ascii")+"nan 0 1 0 -2 1 2 0 -2 0 0 -2 0 0\n");Check(!abum53::LoadFile(dir/"nan.ply",cloud,error),"Reject nonfinite position");
    Text(dir/"zeroq.ply",Header("ascii")+"5 0 1 0 -2 0 2 0 -2 0 0 -2 0 0\n");Check(!abum53::LoadFile(dir/"zeroq.ply",cloud,error),"Reject zero quaternion");
    {auto h=Header("ascii");h.insert(h.find("end_header"),"property float f_rest_0\n");Text(dir/"partial.ply",h);Check(!abum53::LoadFile(dir/"partial.ply",cloud,error),"Reject incomplete SH band");}
    {std::ofstream out(dir/"record.splat",std::ios::binary);for(float v:{1.f,2.f,5.f,.1f,.2f,.3f})Num(out,v);for(uint8_t v:{uint8_t(255),uint8_t(0),uint8_t(128),uint8_t(128),uint8_t(255),uint8_t(128),uint8_t(128),uint8_t(128)})Num(out,v);}
    Check(abum53::LoadFile(dir/"record.splat",cloud,error),error.c_str());const auto rgb=abum53::EvaluateSH(cloud.splats[0].sh,0,0,0,1);Check(Near(rgb[0],1)&&Near(rgb[1],0)&&Near(rgb[2],128/255.),"SPLAT DC color");
    Text(dir/"bad.splat","123");Check(!abum53::LoadFile(dir/"bad.splat",cloud,error),"Reject partial SPLAT record");
    abum53::LoadOptions limited;limited.maxSplats=0;Check(!abum53::LoadFile(dir/"record.splat",cloud,error,limited),"Enforce splat limit");limited.maxSplats=1;limited.maxBytes=1;Check(!abum53::LoadFile(dir/"record.splat",cloud,error,limited),"Enforce byte limit");
    abum53::Cloud container;container.shDegree=3;container.origin[0]=1e12;container.splats.resize(4100);for(size_t i=0;i<container.splats.size();++i){auto& g=container.splats[i];g.position[0]=double(i)/7;g.position[2]=5;g.id=0x100000000ull+i;g.sh[47]=.125f;}
    Check(abum53::WriteContainer(dir/"test.am53",container,error),error.c_str());Check(!abum53::WriteContainer(dir/"test.am53",container,error),"Do not overwrite existing container");
    abum53::ContainerInfo info;Check(abum53::InspectContainer(dir/"test.am53",info,error),error.c_str());Check(info.chunkCount==2&&info.splatCount==4100,"Chunked index");
    Check(abum53::LoadContainerRange(dir/"test.am53",4094,6,cloud,error),error.c_str());Check(cloud.splats.size()==6&&cloud.splats[0].id==container.splats[4094].id&&cloud.origin[0]==1e12&&cloud.splats[5].sh[47]==.125f,"Cross-chunk range and provenance precision");
    Check(!abum53::LoadContainerRange(dir/"test.am53",4099,2,cloud,error),"Reject range overrun");
    {std::fstream file(dir/"test.am53",std::ios::in|std::ios::out|std::ios::binary);file.seekp(130);file.put(char(77));}
    Check(!abum53::LoadFile(dir/"test.am53",cloud,error),"Detect checksum corruption");
    float sh[48]{};sh[3]=1;const auto up=abum53::EvaluateSH(sh,1,0,1,0),down=abum53::EvaluateSH(sh,1,0,-1,0);Check(Near(up[0],.5-.4886025119)&&Near(down[0],.5+.4886025119),"Analytic first-order SH sign");
    float into[3]{};abum53::EvaluateSHInto(sh,1,0,1,0,into);Check(into[0]==up[0]&&into[1]==up[1]&&into[2]==up[2],"DLL-safe SH output matches value API");
    abum53::Cloud imageCloud;imageCloud.splats.resize(2);for(auto& g:imageCloud.splats){g.position[2]=5;g.scale[0]=g.scale[1]=g.scale[2]=.1f;g.opacity=.5f;for(int c=0;c<3;++c)g.sh[c]=float(-.5/.282094791773878143);}
    imageCloud.splats[0].sh[0]=float(.5/.282094791773878143);imageCloud.splats[1].position[2]=6;imageCloud.splats[1].sh[2]=float(.5/.282094791773878143);
    abum53::Camera camera;camera.width=camera.height=17;camera.centerX=camera.centerY=8.5;camera.focalX=camera.focalY=50;abum53::RenderOptions renderOptions;renderOptions.workerCount=1;abum53::RenderResult image;
    Check(abum53::RenderCPU(imageCloud,camera,renderOptions,image,error),error.c_str());const size_t center=(8*17+8)*4;Check(Near(image.rgba[center],.5)&&Near(image.rgba[center+2],.25)&&Near(image.rgba[center+3],.75),"Analytic front-to-back alpha compositing");
    abum53::RenderResult threaded;renderOptions.workerCount=4;Check(abum53::RenderCPU(imageCloud,camera,renderOptions,threaded,error),error.c_str());Check(image.rgba==threaded.rgba,"CPU deterministic across worker counts");Check(abum53::WritePPM(dir/"reference.ppm",image,error),error.c_str());
    imageCloud.splats[0].antialiased=true;Check(abum53::RenderCPU(imageCloud,camera,renderOptions,threaded,error),error.c_str());const double redAA=.5/1.3;Check(Near(threaded.rgba[center],redAA)&&Near(threaded.rgba[center+2],(1-redAA)*.5),"Mixed per-point antialias compensation");
    imageCloud.antialiased=true;Check(abum53::RenderCPU(imageCloud,camera,renderOptions,threaded,error),error.c_str());const double blueAA=.5*(25.0/36.0)/(25.0/36.0+.3);Check(Near(threaded.rgba[center+2],(1-redAA)*blueAA),"Cloud antialias metadata applies to all points");
    imageCloud.antialiased=false;imageCloud.splats[0].antialiased=false;renderOptions.opacityCompensation=true;abum53::RenderResult forcedAA;Check(abum53::RenderCPU(imageCloud,camera,renderOptions,forcedAA,error),error.c_str());Check(threaded.rgba==forcedAA.rgba,"Explicit compensation matches cloud metadata");renderOptions.opacityCompensation=false;
    renderOptions.maxPixelContributions=1;Check(!abum53::RenderCPU(imageCloud,camera,renderOptions,threaded,error),"CPU contribution cap");renderOptions.maxPixelContributions=200000000;imageCloud.splats[0].position[2]=.1;Check(!abum53::RenderCPU(imageCloud,camera,renderOptions,threaded,error),"Explicit near-plane limitation");
    abum53::LoadOptions spzOptions;spzOptions.decompress=abum53::codecs::Decompress;const auto fixtures=std::filesystem::u8path(ABUM53_TEST_FIXTURES);
    for(int version=1;version<=4;++version){
#if !ABUM53_TEST_GZIP
        if(version<4)continue;
#endif
        for(int degree:{0,3}){const auto fixture=fixtures/("spz_v"+std::to_string(version)+"_sh"+std::to_string(degree)+".spz");Check(abum53::LoadFile(fixture,cloud,error,spzOptions),error.c_str());Check(cloud.splats.size()==1&&cloud.shDegree==uint32_t(degree),"SPZ version/degree fixture");const auto& g=cloud.splats[0];Check(Near(g.position[0],1.25)&&Near(g.position[1],-2.5)&&Near(g.position[2],5),"SPZ half/fixed24 position decode");Check(Near(g.scale[0],std::exp(-2.0))&&Near(g.opacity,192/255.0),"SPZ scale/opacity decode");Check(Near(g.sh[0],(128/255.0-.5)/.15),"SPZ wide DC coefficient");Check(cloud.antialiased&&cloud.coordinates==abum53::Coordinates::RUB,"SPZ rendering metadata");if(degree)Check(Near(g.sh[3],.125)&&Near(g.sh[47],-.125),"SPZ SH3 quantization ordering");if(version>=3)Check(g.rotation[0]==0&&g.rotation[1]==0&&g.rotation[2]==0&&g.rotation[3]==1,"SPZ smallest-three identity");}
    }
    Check(!abum53::LoadFile(fixtures/"spz_extensions_rejected.spz",cloud,error,spzOptions),"Reject SPZ unknown-coordinate extensions");Check(!abum53::LoadFile(fixtures/"spz_bad_toc.spz",cloud,error,spzOptions),"Reject SPZ table size mismatch");
    Check(abum53::LoadFile(fixtures/"spz_v4_compressed.spz",cloud,error,spzOptions),error.c_str());Check(cloud.splats.size()==64&&cloud.shDegree==3&&Near(cloud.splats[63].position[1],-2.5)&&Near(cloud.splats[63].sh[47],-.125),"SPZ v4 compressed-block streams");
    Check(abum53::WriteContainer(dir/"spz-preserved.am53",cloud,error),error.c_str());Check(abum53::LoadFile(dir/"spz-preserved.am53",cloud,error),error.c_str());Check(cloud.coordinates==abum53::Coordinates::RUB&&cloud.antialiased,"SPZ metadata survives AM53 conversion");
#if ABUM53_TEST_GZIP
    spzOptions.maxSplats=1;Check(!abum53::LoadFile(fixtures/"spz_gzip_bomb.spz",cloud,error,spzOptions),"Bound gzip decompression");
#endif
    std::cout<<"PASS "<<checks<<" checks; fixtures: "<<dir.string()<<"\n";return 0;
}catch(const std::exception& e){std::cerr<<"FAIL after "<<checks<<" checks: "<<e.what()<<"\n";return 1;}}
