// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
// SPZ quantization/layout compatibility was verified against Niantic/Adobe's MIT implementation.
// See ../SPZ_NOTICE.md. Decompression is supplied by the caller, not an engine dependency.
#include "AbuM53/Core.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace abum53 { namespace spz_detail {
void CheckCancel(const LoadOptions& options){if(options.shouldCancel&&options.shouldCancel())throw std::runtime_error("Import cancelled");}
void Need(bool v,const char* message){if(!v)throw std::runtime_error(message);}
struct Reader {
    const uint8_t* data;uint64_t size,at=0;
    const uint8_t* Take(uint64_t n){Need(at<=size&&n<=size-at,"Truncated SPZ data");const auto* p=data+at;at+=n;return p;}
    uint8_t U8(){return *Take(1);}
    uint32_t U32(){const auto* p=Take(4);return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
    uint64_t U64(){const uint64_t lo=U32();return lo|(uint64_t(U32())<<32);}
};
double Half(const uint8_t* p){const uint16_t bits=uint16_t(p[0])|(uint16_t(p[1])<<8);const int exponent=(bits>>10)&31;const int mantissa=bits&1023;Need(exponent!=31,"SPZ position is nonfinite");const double absolute=exponent?std::ldexp(1.0+mantissa/1024.0,exponent-15):std::ldexp(double(mantissa),-24);return bits&0x8000?-absolute:absolute;}
double Fixed(const uint8_t* p,uint8_t fractional){const uint32_t bits=uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16);const int32_t signedValue=bits&0x800000?int32_t(bits)-0x1000000:int32_t(bits);return std::ldexp(double(signedValue),-int(fractional));}
void Quaternion(const uint8_t* p,uint32_t version,float* output){
    double squared=0;
    if(version<3){for(int i=0;i<3;++i){output[i]=float(double(p[i])/127.5-1);squared+=double(output[i])*output[i];}Need(squared<=1.024,"Invalid SPZ quaternion");output[3]=float(std::sqrt(std::max(0.0,1-squared)));}
    else{Reader reader{p,4};const uint32_t packed=reader.U32(),largest=packed>>30;unsigned slot=0;
        for(uint32_t component=0;component<4;++component){if(component==largest)continue;const uint32_t value=(packed>>(20-10*slot++))&1023;const double magnitude=double(value&511)*(0.7071067811865475244/511.0);output[component]=float(value&512?-magnitude:magnitude);squared+=magnitude*magnitude;}
        Need(squared<=1.00001,"Invalid SPZ smallest-three quaternion");output[largest]=float(std::sqrt(std::max(0.0,1-squared)));
    }
    double norm=0;for(int i=0;i<4;++i)norm+=double(output[i])*output[i];Need(norm>1e-20&&std::isfinite(norm),"Degenerate SPZ quaternion");for(int i=0;i<4;++i)output[i]=float(output[i]/std::sqrt(norm));
}
struct Header{uint32_t version,count;uint8_t degree,fractional,flags,streams;};
Header ReadHeader(Reader& reader){Need(reader.U32()==0x5053474eu,"Invalid SPZ NGSP magic");Header h;h.version=reader.U32();h.count=reader.U32();h.degree=reader.U8();h.fractional=reader.U8();h.flags=reader.U8();h.streams=reader.U8();return h;}
void ValidateHeader(const Header& h,const LoadOptions& options){Need(h.version>=1&&h.version<=4,"Unsupported SPZ version");Need(h.degree<=3,"SPZ SH degree above 3 is not supported");Need(h.fractional<=30,"SPZ fractional bits exceed supported range");Need((h.flags&~1u)==0,"SPZ extensions/unknown flags require an explicit coordinate/appearance adapter");Need(h.count<=options.maxSplats&&uint64_t(h.count)<=options.maxBytes/sizeof(Gaussian),"SPZ decoded cloud exceeds configured limit");}
void Convert(const Header& h,const std::array<const uint8_t*,6>& streams,Cloud& output,const LoadOptions& options){
    Cloud cloud;cloud.shDegree=h.degree;cloud.antialiased=(h.flags&1)!=0;cloud.coordinates=Coordinates::RUB;cloud.splats.resize(h.count);
    const uint32_t remainder=3*((h.degree+1)*(h.degree+1)-1),positionStride=h.version==1?6:9,rotationStride=h.version>=3?4:3;
    for(uint32_t i=0;i<h.count;++i){if(i%4096==0)CheckCancel(options);auto& g=cloud.splats[i];g.id=i;
        for(int axis=0;axis<3;++axis){const uint8_t* p=streams[0]+uint64_t(i)*positionStride+axis*(h.version==1?2:3);g.position[axis]=h.version==1?Half(p):Fixed(p,h.fractional);g.scale[axis]=float(std::exp(double(streams[3][uint64_t(i)*3+axis])/16-10));g.sh[axis]=float((double(streams[2][uint64_t(i)*3+axis])/255-.5)/.15);}
        g.opacity=streams[1][i]/255.f;Quaternion(streams[4]+uint64_t(i)*rotationStride,h.version,g.rotation);
        for(uint32_t coefficient=0;coefficient<remainder;++coefficient)g.sh[3+coefficient]=(int(streams[5][uint64_t(i)*remainder+coefficient])-128)/128.f;
    }
    CheckCancel(options);output=std::move(cloud);
}
} // namespace spz_detail
bool DecodeSPZ(const uint8_t* data,uint64_t bytes,Cloud& output,std::string& error,const LoadOptions& options){
    using namespace spz_detail;
    try{error.clear();CheckCancel(options);Need(data&&bytes>=2&&bytes<=options.maxBytes,"SPZ input missing or exceeds byte limit");Need(options.decompress!=nullptr,"SPZ requires an installed bounded gzip/Zstandard decompression provider");
        std::vector<uint8_t> legacy;bool compressedLegacy=data[0]==0x1f&&data[1]==0x8b;
        if(compressedLegacy){const uint64_t pointLimit=std::min<uint64_t>(options.maxSplats,(std::numeric_limits<uint64_t>::max()-16)/65);const uint64_t limit=std::min(options.maxBytes,16+pointLimit*65);const bool decompressed=options.decompress(Compression::Gzip,data,bytes,0,limit,legacy,error);Need(decompressed,error.empty()?"SPZ gzip decompression failed":error.c_str());Need(legacy.size()<=limit,"SPZ provider exceeded output budget");data=legacy.data();bytes=legacy.size();}
        Reader reader{data,bytes};const Header h=ReadHeader(reader);ValidateHeader(h,options);
        Need(compressedLegacy?h.version<=3:h.version==4,"SPZ version does not match compression envelope");
        const uint64_t count=h.count;const std::array<uint64_t,6> sizes={count*(h.version==1?6u:9u),count,count*3,count*3,count*(h.version>=3?4u:3u),count*3*((h.degree+1)*(h.degree+1)-1)};
        std::array<const uint8_t*,6> streams{};std::array<std::vector<uint8_t>,6> decoded;
        if(compressedLegacy){Need(h.streams==0,"Unknown SPZ legacy reserved field");for(size_t i=0;i<6;++i)streams[i]=reader.Take(sizes[i]);Need(reader.at==reader.size,"SPZ legacy stream has trailing data");}
        else{const uint32_t toc=reader.U32();for(int i=0;i<12;++i)Need(reader.U8()==0,"SPZ v4 reserved fields are nonzero");Need(toc==32,"SPZ extension zones are not supported without a coordinate adapter");
            const uint32_t expectedStreams=h.count==0?0:h.degree?6:5;Need(h.streams==expectedStreams,"SPZ v4 stream count mismatch");
            std::array<uint64_t,6> compressedSizes{};uint64_t end=32+uint64_t(h.streams)*16;Need(end<=bytes,"Truncated SPZ table of contents");
            for(uint32_t i=0;i<h.streams;++i){compressedSizes[i]=reader.U64();Need(reader.U64()==sizes[i],"SPZ v4 uncompressed stream size mismatch");Need(compressedSizes[i]>0&&end<=bytes&&compressedSizes[i]<=bytes-end,"SPZ v4 compressed stream outside file");end+=compressedSizes[i];}
            Need(end==bytes,"SPZ v4 has trailing or missing data");
            uint64_t offset=reader.at;for(uint32_t i=0;i<h.streams;++i){CheckCancel(options);Need(sizes[i]<=options.maxBytes,"SPZ stream exceeds byte limit");const bool decompressed=options.decompress(Compression::Zstd,data+offset,compressedSizes[i],sizes[i],sizes[i],decoded[i],error);Need(decompressed,error.empty()?"SPZ Zstandard decompression failed":error.c_str());Need(decoded[i].size()==sizes[i],"SPZ provider returned incorrect decompressed size");streams[i]=decoded[i].data();offset+=compressedSizes[i];}
        }
        CheckCancel(options);Convert(h,streams,output,options);return true;
    }catch(const std::exception& e){error=e.what();return false;}catch(...){error="Unknown SPZ decoding error";return false;}
}
} // namespace abum53
