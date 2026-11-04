// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53/Core.h"
#include "AbuM53/Codecs.h"
#include <chrono>
#include <cstdlib>
#include <iostream>

int main(int argc,char** argv){
    if(argc<3){std::cout<<"Abu M53 portable converter\n"
        "  M53Convert inspect INPUT.ply|splat|am53\n"
        "  M53Convert convert INPUT OUTPUT.am53\n"
        "  M53Convert render INPUT OUTPUT.ppm [cameraX cameraY cameraZ]\n"
        "PLY uses Graphdeco log-scale/logit-opacity fields. No automatic coordinate conversion.\n"
        "CPU preview camera points along +Z, +Y up. Output values retain source blend space.\n";return 2;}
    std::string error;abum53::Cloud cloud;const auto start=std::chrono::steady_clock::now();
    abum53::LoadOptions loadOptions;loadOptions.decompress=abum53::codecs::Decompress;
    if(!abum53::LoadFile(std::filesystem::u8path(argv[2]),cloud,error,loadOptions)){std::cerr<<"Import failed: "<<error<<"\n";return 1;}
    const std::string command=argv[1];
    if(command=="inspect"){
        std::cout<<"splats="<<cloud.splats.size()<<" sh_degree="<<cloud.shDegree<<" decoded_bytes="<<cloud.splats.size()*sizeof(abum53::Gaussian)<<"\n";
    }else if(command=="convert"&&argc==4){
        if(!abum53::WriteContainer(std::filesystem::u8path(argv[3]),cloud,error)){std::cerr<<"Conversion failed: "<<error<<"\n";return 1;}
        std::cout<<"Wrote "<<cloud.splats.size()<<" splats with CRC32 chunk checksums.\n";
    }else if(command=="render"&&(argc==4||argc==7)){
        abum53::Camera camera;if(argc==7)for(int i=0;i<3;++i){char* end=nullptr;camera.position[i]=std::strtod(argv[4+i],&end);if(!end||*end){std::cerr<<"Invalid camera value\n";return 2;}}
        abum53::RenderOptions options;abum53::RenderResult image;
        if(!abum53::RenderCPU(cloud,camera,options,image,error)||!abum53::WritePPM(std::filesystem::u8path(argv[3]),image,error)){std::cerr<<"Render failed: "<<error<<"\n";return 1;}
        std::cout<<"projected_splats="<<image.projectedSplats<<" contributions="<<image.pixelContributions<<"\n";
    }else{std::cerr<<"Unknown command or incorrect argument count\n";return 2;}
    std::cout<<"elapsed_ms="<<std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count()<<"\n";return 0;
}
