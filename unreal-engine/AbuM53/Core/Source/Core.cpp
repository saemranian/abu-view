// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53/Core.h"
#include <algorithm>
#include <atomic>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <system_error>

namespace abum53 { namespace {
constexpr double DC = 0.282094791773878143;
constexpr uint32_t RecordBytes = 256, HeaderBytes = 80, EntryBytes = 24, PageSplats = 4096;
struct Failure : std::runtime_error { using std::runtime_error::runtime_error; };
void Require(bool value, const char* message) { if (!value) throw Failure(message); }
void CheckCancel(const LoadOptions& options) { Require(!options.shouldCancel || !options.shouldCancel(), "Import cancelled"); }
bool LittleHost() { uint16_t v=1; return *reinterpret_cast<unsigned char*>(&v)==1; }
template<class T> T ReadNumber(std::istream& in, bool little=true) {
    unsigned char b[sizeof(T)]; in.read(reinterpret_cast<char*>(b),sizeof(T));
    Require(bool(in),"Truncated binary attribute");
    if (LittleHost()!=little) std::reverse(b,b+sizeof(T));
    T v; std::memcpy(&v,b,sizeof(T)); return v;
}
template<class T> void WriteNumber(std::ostream& out,T value) {
    unsigned char b[sizeof(T)];std::memcpy(b,&value,sizeof(T));
    if(!LittleHost()) std::reverse(b,b+sizeof(T));
    out.write(reinterpret_cast<const char*>(b),sizeof(T));
    Require(bool(out),"Failed writing container");
}
uint64_t FileSize(const std::filesystem::path& p,const LoadOptions& o) {
    std::error_code ec;const auto n=std::filesystem::file_size(p,ec);
    Require(!ec,"Cannot inspect input file");Require(n<=o.maxBytes,"Input exceeds configured byte limit");return n;
}
uint64_t Count(const std::string& s) {
    uint64_t n=0;auto r=std::from_chars(s.data(),s.data()+s.size(),n);
    Require(r.ec==std::errc()&&r.ptr==s.data()+s.size(),"Invalid unsigned count");return n;
}
std::string Token(std::istream& in) {
    std::string s; char c;
    while(in.get(c)&&std::isspace(static_cast<unsigned char>(c))) {}
    Require(bool(in),"Truncated ASCII data");
    do { Require(s.size()<128,"ASCII token exceeds limit");s+=c; }
    while(in.get(c)&&!std::isspace(static_cast<unsigned char>(c)));
    return s;
}
double Real(const std::string& s) {
    double v=0;auto r=std::from_chars(s.data(),s.data()+s.size(),v);
    Require(r.ec==std::errc()&&r.ptr==s.data()+s.size(),"Invalid numeric attribute");return v;
}
bool HeaderLine(std::istream& in,std::string& line){line.clear();char c;while(in.get(c)){if(c=='\n')return true;Require(line.size()<65536,"PLY header line exceeds limit");line+=c;}return !line.empty();}
void Validate(Gaussian& g,uint32_t degree) {
    Require(degree<=3,"Unsupported SH degree");
    double norm=0;
    for(int i=0;i<3;++i) {Require(std::isfinite(g.position[i]),"Nonfinite position");Require(std::isfinite(g.scale[i])&&g.scale[i]>0,"Invalid scale");}
    for(float q:g.rotation) {Require(std::isfinite(q),"Nonfinite quaternion");norm+=double(q)*q;}
    Require(norm>1e-20&&std::isfinite(norm),"Degenerate quaternion");
    if(std::abs(norm-1.0)>2e-6){const double inv=1/std::sqrt(norm);for(float& q:g.rotation)q=static_cast<float>(q*inv);}
    Require(std::isfinite(g.opacity)&&g.opacity>=0&&g.opacity<=1,"Opacity outside [0,1]");
    const uint32_t scalars=3*(degree+1)*(degree+1);
    for(uint32_t i=0;i<scalars;++i)Require(std::isfinite(g.sh[i]),"Nonfinite SH coefficient");
}
enum class Scalar { I8,U8,I16,U16,I32,U32,F32,F64 };
Scalar Type(const std::string& t) {
    if(t=="char"||t=="int8")return Scalar::I8;if(t=="uchar"||t=="uint8")return Scalar::U8;
    if(t=="short"||t=="int16")return Scalar::I16;if(t=="ushort"||t=="uint16")return Scalar::U16;
    if(t=="int"||t=="int32")return Scalar::I32;if(t=="uint"||t=="uint32")return Scalar::U32;
    if(t=="float"||t=="float32")return Scalar::F32;if(t=="double"||t=="float64")return Scalar::F64;
    throw Failure("Unsupported PLY scalar type");
}
bool Integer(Scalar s){return s!=Scalar::F32&&s!=Scalar::F64;}
double Value(std::istream& in,Scalar s,bool ascii,bool little) {
    if(ascii) {
        const double v=Real(Token(in));
        if(Integer(s)) {
            double lo=0,hi=0;
            switch(s){case Scalar::I8:lo=-128;hi=127;break;case Scalar::U8:hi=255;break;case Scalar::I16:lo=-32768;hi=32767;break;case Scalar::U16:hi=65535;break;case Scalar::I32:lo=-2147483648.0;hi=2147483647;break;case Scalar::U32:hi=4294967295.0;break;default:break;}
            Require(std::isfinite(v)&&v==std::floor(v)&&v>=lo&&v<=hi,"PLY integer is out of range");
        }
        return v;
    }
    switch(s){case Scalar::I8:return ReadNumber<int8_t>(in,little);case Scalar::U8:return ReadNumber<uint8_t>(in,little);
        case Scalar::I16:return ReadNumber<int16_t>(in,little);case Scalar::U16:return ReadNumber<uint16_t>(in,little);
        case Scalar::I32:return ReadNumber<int32_t>(in,little);case Scalar::U32:return ReadNumber<uint32_t>(in,little);
        case Scalar::F32:return ReadNumber<float>(in,little);case Scalar::F64:return ReadNumber<double>(in,little);}
    throw Failure("Unknown scalar type");
}
struct Property { std::string name;Scalar value;Scalar count=Scalar::U8;bool list=false; };
struct Element { std::string name;uint64_t count;std::vector<Property> properties; };
size_t ScalarBytes(Scalar s) {
    switch(s){case Scalar::I8:case Scalar::U8:return 1;case Scalar::I16:case Scalar::U16:return 2;
        case Scalar::I32:case Scalar::U32:case Scalar::F32:return 4;case Scalar::F64:return 8;}
    throw Failure("Unknown scalar type");
}
template<class T> T MemoryNumber(const uint8_t* bytes,bool swap) {
    T value;
    if(!swap)std::memcpy(&value,bytes,sizeof(T));
    else {uint8_t reversed[sizeof(T)];std::reverse_copy(bytes,bytes+sizeof(T),reversed);std::memcpy(&value,reversed,sizeof(T));}
    return value;
}
double MemoryValue(const uint8_t* bytes,Scalar s,bool swap) {
    switch(s){case Scalar::I8:return MemoryNumber<int8_t>(bytes,swap);case Scalar::U8:return MemoryNumber<uint8_t>(bytes,swap);
        case Scalar::I16:return MemoryNumber<int16_t>(bytes,swap);case Scalar::U16:return MemoryNumber<uint16_t>(bytes,swap);
        case Scalar::I32:return MemoryNumber<int32_t>(bytes,swap);case Scalar::U32:return MemoryNumber<uint32_t>(bytes,swap);
        case Scalar::F32:return MemoryNumber<float>(bytes,swap);case Scalar::F64:return MemoryNumber<double>(bytes,swap);}
    throw Failure("Unknown scalar type");
}
void LoadPly(std::istream& in,uint64_t fileBytes,Cloud& out,const LoadOptions& options) {
    std::string line;HeaderLine(in,line);if(!line.empty()&&line.back()=='\r')line.pop_back();Require(line=="ply","Invalid PLY magic");
    bool ascii=false,little=true,format=false,ended=false;uint64_t headerSize=4;
    std::vector<Element> elements;
    while(HeaderLine(in,line)) {
        headerSize+=line.size()+1;Require(headerSize<=1024*1024,"PLY header exceeds limit");
        std::istringstream ls(line);std::string keyword;ls>>keyword;
        if(keyword=="end_header"){ended=true;break;}
        if(keyword=="comment"||keyword=="obj_info"||keyword.empty())continue;
        if(keyword=="format") {
            std::string name,version;ls>>name>>version;Require(!format&&version=="1.0","Unsupported PLY format/version");format=true;
            if(name=="ascii")ascii=true;else if(name=="binary_little_endian")little=true;else if(name=="binary_big_endian")little=false;else throw Failure("Unsupported PLY encoding");
        } else if(keyword=="element") {
            std::string name,count;ls>>name>>count;Require(!name.empty()&&!count.empty(),"Malformed PLY element");
            Require(elements.size()<128,"Too many PLY elements");elements.push_back({name,Count(count),{}});
        } else if(keyword=="property") {
            Require(!elements.empty(),"Property without element");Require(elements.back().properties.size()<1024,"Too many PLY properties");
            std::string type,name;ls>>type;Property p{};
            if(type=="list"){std::string ct,vt;ls>>ct>>vt>>name;p.list=true;p.count=Type(ct);p.value=Type(vt);Require(Integer(p.count),"Noninteger PLY list count");}
            else {ls>>name;p.value=Type(type);}Require(!name.empty(),"Unnamed PLY property");p.name=name;
            for(const auto& old:elements.back().properties)Require(old.name!=name,"Duplicate PLY property");
            elements.back().properties.push_back(p);
        } else throw Failure("Unknown PLY header statement");
    }
    Require(ended&&format,"Incomplete PLY header");
    for(const auto& element:elements)Require(element.count==0||!element.properties.empty(),"Nonempty PLY element has no properties");
    int vertex=-1;for(size_t i=0;i<elements.size();++i)if(elements[i].name=="vertex"){Require(vertex<0,"Duplicate vertex element");vertex=int(i);}
    Require(vertex>=0,"PLY has no vertex element");const auto& ve=elements[vertex];
    Require(ve.count<=options.maxSplats&&ve.count<=options.maxBytes/sizeof(Gaussian),"PLY decoded cloud exceeds configured limit");
    auto index=[&](const std::string& name){for(size_t i=0;i<ve.properties.size();++i)if(ve.properties[i].name==name){Require(!ve.properties[i].list,"Gaussian attribute cannot be a list");return int(i);}return -1;};
    int pos[3],scale[3],rot[4],dc[3];
    const char* xyz[]={"x","y","z"};
    for(int i=0;i<3;++i){pos[i]=index(xyz[i]);scale[i]=index("scale_"+std::to_string(i));dc[i]=index("f_dc_"+std::to_string(i));Require(pos[i]>=0&&scale[i]>=0&&dc[i]>=0,"PLY is not a supported Gaussian profile: position, log scale and SH DC required");}
    for(int i=0;i<4;++i){rot[i]=index("rot_"+std::to_string(i));Require(rot[i]>=0,"PLY Gaussian quaternion is missing");}
    const int opacity=index("opacity");Require(opacity>=0,"PLY Gaussian opacity is missing");
    int restCount=0;for(const auto& p:ve.properties)if(p.name.rfind("f_rest_",0)==0)++restCount;
    Require(restCount==0||restCount==9||restCount==24||restCount==45,"Incomplete/unsupported spherical harmonic bands");
    out.shDegree=restCount==0?0:restCount==9?1:restCount==24?2:3;
    std::vector<int> rest;for(int i=0;i<restCount;++i){int p=index("f_rest_"+std::to_string(i));Require(p>=0,"Noncontiguous SH properties");rest.push_back(p);}
    // Reject impossible binary bodies before reserving a potentially large decoded cloud.
    if(!ascii){const auto bodyStart=in.tellg();Require(bodyStart>=0&&uint64_t(bodyStart)<=fileBytes,"Invalid PLY body offset");
        uint64_t remaining=fileBytes-uint64_t(bodyStart);
        for(const auto& el:elements){uint64_t minimumStride=0;for(const auto& p:el.properties)minimumStride+=ScalarBytes(p.list?p.count:p.value);
            Require(!minimumStride||el.count<=remaining/minimumStride,"Truncated binary PLY body");remaining-=el.count*minimumStride;}}
    CheckCancel(options);
    out.splats.reserve(static_cast<size_t>(ve.count));
    auto append=[&](const std::vector<double>& values,uint64_t n){
        Gaussian g;g.id=n;
        for(int i=0;i<3;++i){g.position[i]=values[pos[i]];g.scale[i]=static_cast<float>(std::exp(values[scale[i]]));g.sh[i]=static_cast<float>(values[dc[i]]);}
        for(int i=0;i<4;++i)g.rotation[i]=static_cast<float>(values[rot[(i+1)%4]]);
        const double logit=values[opacity];Require(std::isfinite(logit),"Nonfinite opacity logit");
        g.opacity=static_cast<float>(logit>=0?1/(1+std::exp(-logit)):std::exp(logit)/(1+std::exp(logit)));
        const int perChannel=restCount/3;
        for(int c=0;c<3;++c)for(int b=0;b<perChannel;++b)g.sh[(b+1)*3+c]=static_cast<float>(values[rest[c*perChannel+b]]);
        Validate(g,out.shDegree);out.splats.push_back(g);
    };
    for(size_t e=0;e<elements.size();++e) {
        const auto& el=elements[e];Require(el.count<=options.maxBytes,"Unreasonable PLY element count");
        std::vector<double> values(e==size_t(vertex)?el.properties.size():0);
        if(!ascii&&e==size_t(vertex)&&std::none_of(el.properties.begin(),el.properties.end(),[](const Property& p){return p.list;})){
            // Fixed-stride binary vertices: one bounded read per chunk, rather than one read per attribute.
            std::vector<size_t> offsets;size_t stride=0;
            for(const auto& p:el.properties){offsets.push_back(stride);stride+=ScalarBytes(p.value);}
            const size_t chunkRows=std::min<size_t>(4096,std::max<size_t>(1,(1024*1024)/stride));
            std::vector<uint8_t> bytes(chunkRows*stride);const bool swap=LittleHost()!=little;
            for(uint64_t first=0;first<el.count;first+=chunkRows){CheckCancel(options);
                const auto rows=static_cast<size_t>(std::min<uint64_t>(chunkRows,el.count-first));
                in.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(rows*stride));Require(bool(in),"Truncated binary PLY chunk");
                for(size_t row=0;row<rows;++row){const uint8_t* source=bytes.data()+row*stride;
                    for(size_t p=0;p<el.properties.size();++p)values[p]=MemoryValue(source+offsets[p],el.properties[p].value,swap);
                    append(values,first+row);}
            }
            continue;
        }
        for(uint64_t n=0;n<el.count;++n) {
            if(n%4096==0)CheckCancel(options);
            for(size_t p=0;p<el.properties.size();++p){const auto& prop=el.properties[p];
                if(prop.list){const double c=Value(in,prop.count,ascii,little);Require(std::isfinite(c)&&c>=0&&c<=1048576&&c==std::floor(c),"PLY list exceeds limit");for(uint64_t j=0;j<uint64_t(c);++j){if(j%4096==0)CheckCancel(options);(void)Value(in,prop.value,ascii,little);}}
                else{double v=Value(in,prop.value,ascii,little);if(!values.empty())values[p]=v;}
            }
            if(e!=size_t(vertex))continue;
            append(values,n);
        }
    }
}
void LoadSplat(std::istream& in,uint64_t size,Cloud& out,const LoadOptions& options){
    Require(size%32==0,"SPLAT length is not a multiple of 32");const uint64_t count=size/32;
    Require(count<=options.maxSplats&&count<=options.maxBytes/sizeof(Gaussian),"SPLAT decoded cloud exceeds configured limit");
    out.splats.reserve(static_cast<size_t>(count));out.shDegree=0;
    for(uint64_t n=0;n<count;++n){if(n%4096==0)CheckCancel(options);Gaussian g;g.id=n;for(double& p:g.position)p=ReadNumber<float>(in);for(float& s:g.scale)s=ReadNumber<float>(in);
        for(int c=0;c<3;++c)g.sh[c]=static_cast<float>((ReadNumber<uint8_t>(in)/255.0-.5)/DC);
        g.opacity=ReadNumber<uint8_t>(in)/255.f;float q[4];for(float& v:q)v=(ReadNumber<uint8_t>(in)-128)/128.f;
        for(int i=0;i<4;++i)g.rotation[i]=q[(i+1)%4];Validate(g,0);out.splats.push_back(g);
    }
}
uint32_t CRC(const unsigned char* bytes,size_t count){
    uint32_t crc=0xffffffffu;
    for(size_t i=0;i<count;++i){crc^=bytes[i];for(int b=0;b<8;++b)crc=(crc>>1)^(0xedb88320u&uint32_t(0-int32_t(crc&1)));}
    return ~crc;
}
struct Entry{uint64_t offset;uint32_t count,bytes,crc;};
struct Index{ContainerInfo info;std::vector<Entry> entries;};
Index ReadIndex(std::istream& in,uint64_t size,const LoadOptions& options){
    Require(size>=HeaderBytes,"Truncated AM53 header");char magic[8];in.read(magic,8);Require(std::memcmp(magic,"ABUM53\0\0",8)==0,"Invalid AM53 magic");
    Require(ReadNumber<uint32_t>(in)==1,"Unsupported AM53 major version");Require(ReadNumber<uint32_t>(in)==HeaderBytes,"Unsupported AM53 header size");
    Index result;auto& info=result.info;info.splatCount=ReadNumber<uint64_t>(in);info.shDegree=ReadNumber<uint32_t>(in);info.chunkSplats=ReadNumber<uint32_t>(in);
    for(double& v:info.origin){v=ReadNumber<double>(in);Require(std::isfinite(v),"Nonfinite AM53 origin");}
    const auto indexOffset=ReadNumber<uint64_t>(in);info.chunkCount=ReadNumber<uint32_t>(in);
    const uint32_t flags=ReadNumber<uint32_t>(in);Require((flags&~3u)==0,"Unsupported AM53 flags");info.antialiased=(flags&1)!=0;info.coordinates=(flags&2)?Coordinates::RUB:Coordinates::Unspecified;Require(ReadNumber<uint64_t>(in)==size,"AM53 file length mismatch");
    Require(info.shDegree<=3&&info.chunkSplats>0&&info.chunkSplats<=1048576,"Invalid AM53 layout");
    Require(info.splatCount<=options.maxSplats,"AM53 source count exceeds configured limit");
    const uint64_t expected=info.splatCount/info.chunkSplats+(info.splatCount%info.chunkSplats!=0);
    Require(expected==info.chunkCount,"AM53 chunk count mismatch");
    Require(indexOffset==HeaderBytes&&uint64_t(info.chunkCount)<=(size-HeaderBytes)/EntryBytes,"AM53 index outside file");
    uint64_t offset=HeaderBytes+uint64_t(info.chunkCount)*EntryBytes,remaining=info.splatCount;
    result.entries.reserve(info.chunkCount);
    for(uint32_t i=0;i<info.chunkCount;++i){Entry e;e.offset=ReadNumber<uint64_t>(in);e.count=ReadNumber<uint32_t>(in);e.bytes=ReadNumber<uint32_t>(in);e.crc=ReadNumber<uint32_t>(in);Require(ReadNumber<uint32_t>(in)==0,"Unknown AM53 chunk encoding");
        Require(e.offset==offset&&e.count==std::min<uint64_t>(remaining,info.chunkSplats)&&uint64_t(e.count)*RecordBytes==e.bytes,"Invalid AM53 chunk range");
        Require(e.offset<=size&&e.bytes<=size-e.offset,"AM53 chunk outside file");offset+=e.bytes;remaining-=e.count;result.entries.push_back(e);
    }
    Require(offset==size&&remaining==0,"AM53 trailing or missing data");return result;
}
Gaussian DecodeRecord(std::istream& in,uint32_t degree){Gaussian g;for(double& v:g.position)v=ReadNumber<double>(in);for(float& v:g.scale)v=ReadNumber<float>(in);for(float& v:g.rotation)v=ReadNumber<float>(in);g.opacity=ReadNumber<float>(in);for(float& v:g.sh)v=ReadNumber<float>(in);g.id=ReadNumber<uint64_t>(in);Validate(g,degree);return g;}
void EncodeRecord(std::ostream& out,const Gaussian& g){for(double v:g.position)WriteNumber(out,v);for(float v:g.scale)WriteNumber(out,v);for(float v:g.rotation)WriteNumber(out,v);WriteNumber(out,g.opacity);for(float v:g.sh)WriteNumber(out,v);WriteNumber(out,g.id);}
void ReadRange(std::istream& in,const Index& index,uint64_t first,uint64_t count,Cloud& result,const LoadOptions& options){
    Require(first<=index.info.splatCount&&count<=index.info.splatCount-first,"AM53 requested range is outside cloud");
    Require(count<=options.maxSplats&&count<=options.maxBytes/sizeof(Gaussian),"AM53 decoded range exceeds limit");
    result.shDegree=index.info.shDegree;result.antialiased=index.info.antialiased;result.coordinates=index.info.coordinates;std::copy(index.info.origin,index.info.origin+3,result.origin);result.splats.reserve(static_cast<size_t>(count));
    if(count==0)return;
    const uint64_t last=first+count;
    for(uint64_t page=first/index.info.chunkSplats;page<index.entries.size()&&page*index.info.chunkSplats<last;++page){CheckCancel(options);const auto& e=index.entries[size_t(page)];std::string bytes(e.bytes,'\0');in.seekg(static_cast<std::streamoff>(e.offset));in.read(bytes.data(),e.bytes);Require(bool(in),"Truncated AM53 chunk");Require(CRC(reinterpret_cast<const unsigned char*>(bytes.data()),bytes.size())==e.crc,"AM53 checksum mismatch");
        const uint64_t base=page*index.info.chunkSplats;const uint64_t begin=std::max(first,base)-base,end=std::min(last,base+e.count)-base;
        std::istringstream data(bytes,std::ios::in|std::ios::binary);data.seekg(static_cast<std::streamoff>(begin*RecordBytes));
        for(uint64_t n=begin;n<end;++n)result.splats.push_back(DecodeRecord(data,index.info.shDegree));
    }
}
template<class Fn> bool Guard(std::string& error,Fn&& fn){try{error.clear();fn();return true;}catch(const std::exception& e){error=e.what();return false;}catch(...){error="Unknown core error";return false;}}
} // anonymous

bool LoadFile(const std::filesystem::path& path,Cloud& output,std::string& error,const LoadOptions& options){return Guard(error,[&]{CheckCancel(options);const uint64_t size=FileSize(path,options);std::ifstream in(path,std::ios::binary);Require(bool(in),"Cannot open input file");Cloud result;
    std::string ext=path.extension().string();std::transform(ext.begin(),ext.end(),ext.begin(),[](unsigned char c){return char(std::tolower(c));});
    if(ext==".ply")LoadPly(in,size,result,options);else if(ext==".splat")LoadSplat(in,size,result,options);else if(ext==".am53"){auto index=ReadIndex(in,size,options);ReadRange(in,index,0,index.info.splatCount,result,options);}else if(ext==".spz"){std::vector<uint8_t> bytes(static_cast<size_t>(size));in.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(size));Require(bool(in),"Truncated SPZ file");const bool decoded=DecodeSPZ(bytes.data(),bytes.size(),result,error,options);Require(decoded,error.c_str());}else throw Failure("Unsupported format; supported: Gaussian .ply, .splat, .spz, .am53");CheckCancel(options);output=std::move(result);});}
bool InspectContainer(const std::filesystem::path& path,ContainerInfo& info,std::string& error,const LoadOptions& options){return Guard(error,[&]{const auto size=FileSize(path,options);std::ifstream in(path,std::ios::binary);Require(bool(in),"Cannot open AM53 file");info=ReadIndex(in,size,options).info;});}
bool LoadContainerRange(const std::filesystem::path& path,uint64_t first,uint64_t count,Cloud& output,std::string& error,const LoadOptions& options){return Guard(error,[&]{const auto size=FileSize(path,options);std::ifstream in(path,std::ios::binary);Require(bool(in),"Cannot open AM53 file");auto index=ReadIndex(in,size,options);Cloud result;ReadRange(in,index,first,count,result,options);CheckCancel(options);output=std::move(result);});}
bool WriteContainer(const std::filesystem::path& path,const Cloud& cloud,std::string& error){
    std::filesystem::path temporary;
    const bool okay=Guard(error,[&]{Require(cloud.shDegree<=3,"Unsupported SH degree");Require(!std::filesystem::exists(path),"Output exists; choose a new file to preserve existing data");
        for(double v:cloud.origin)Require(std::isfinite(v),"Nonfinite source origin");
        const uint64_t count=cloud.splats.size(),chunks=count/PageSplats+(count%PageSplats!=0);
        Require(chunks<=std::numeric_limits<uint32_t>::max()&&count<=(std::numeric_limits<uint64_t>::max()-HeaderBytes-chunks*EntryBytes)/RecordBytes,"Cloud is too large");
        const uint64_t total=HeaderBytes+chunks*EntryBytes+count*RecordBytes;
        static std::atomic<uint64_t> serial{0};temporary=path;temporary+=L".writing."+std::to_wstring(std::chrono::steady_clock::now().time_since_epoch().count())+L"."+std::to_wstring(serial++);
        std::ofstream out(temporary,std::ios::binary|std::ios::trunc);Require(bool(out),"Cannot create output file");out.write("ABUM53\0\0",8);WriteNumber(out,uint32_t(1));WriteNumber(out,HeaderBytes);WriteNumber(out,count);WriteNumber(out,cloud.shDegree);WriteNumber(out,PageSplats);for(double v:cloud.origin)WriteNumber(out,v);WriteNumber(out,uint64_t(HeaderBytes));WriteNumber(out,uint32_t(chunks));WriteNumber(out,uint32_t((cloud.antialiased?1:0)|(cloud.coordinates==Coordinates::RUB?2:0)));WriteNumber(out,total);
        for(uint64_t i=0;i<chunks;++i){WriteNumber(out,uint64_t(0));for(int j=0;j<4;++j)WriteNumber(out,uint32_t(0));}
        std::vector<Entry> entries;entries.reserve(static_cast<size_t>(chunks));
        for(uint64_t page=0;page<chunks;++page){const uint64_t first=page*PageSplats;const uint32_t n=static_cast<uint32_t>(std::min<uint64_t>(PageSplats,count-first));std::ostringstream data(std::ios::out|std::ios::binary);
            for(uint32_t i=0;i<n;++i){Gaussian g=cloud.splats[size_t(first+i)];Validate(g,cloud.shDegree);EncodeRecord(data,g);}
            const auto bytes=data.str();Entry e{static_cast<uint64_t>(out.tellp()),n,static_cast<uint32_t>(bytes.size()),CRC(reinterpret_cast<const unsigned char*>(bytes.data()),bytes.size())};out.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));Require(bool(out),"Failed writing chunk");entries.push_back(e);
        }
        out.seekp(HeaderBytes);for(const auto& e:entries){WriteNumber(out,e.offset);WriteNumber(out,e.count);WriteNumber(out,e.bytes);WriteNumber(out,e.crc);WriteNumber(out,uint32_t(0));}out.flush();Require(bool(out),"Failed flushing output");out.close();std::filesystem::rename(temporary,path);temporary.clear();
    });
    if(!temporary.empty()){std::error_code ec;std::filesystem::remove(temporary,ec);}return okay;
}
std::array<float,3> EvaluateSH(const float* sh,uint32_t degree,double x,double y,double z){
    degree=std::min(degree,3u);const double length=std::sqrt(x*x+y*y+z*z);if(length>1e-20){x/=length;y/=length;z/=length;}else{x=0;y=0;z=1;}
    double b[16]{};b[0]=DC;
    if(degree>=1){constexpr double c=0.4886025119029199;b[1]=-c*y;b[2]=c*z;b[3]=-c*x;}
    if(degree>=2){b[4]=1.0925484305920792*x*y;b[5]=-1.0925484305920792*y*z;b[6]=0.31539156525252005*(3*z*z-1);b[7]=-1.0925484305920792*x*z;b[8]=0.5462742152960396*(x*x-y*y);}
    if(degree>=3){b[9]=-0.5900435899266435*y*(3*x*x-y*y);b[10]=2.890611442640554*x*y*z;b[11]=-0.4570457994644658*y*(5*z*z-1);b[12]=0.3731763325901154*z*(5*z*z-3);b[13]=-0.4570457994644658*x*(5*z*z-1);b[14]=1.445305721320277*z*(x*x-y*y);b[15]=-0.5900435899266435*x*(x*x-3*y*y);}
    std::array<float,3> result{};for(int c=0;c<3;++c){double value=.5;for(uint32_t i=0;i<(degree+1)*(degree+1);++i)value+=b[i]*sh[i*3+c];result[c]=static_cast<float>(std::max(0.0,value));}return result;
}
void EvaluateSHInto(const float* sh,uint32_t degree,double x,double y,double z,float* output){
    const auto result=EvaluateSH(sh,degree,x,y,z);std::copy(result.begin(),result.end(),output);
}
} // namespace abum53

