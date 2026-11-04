// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53/Codecs.h"
#include "zstd.h"
#include <algorithm>
#include <array>
#include <limits>
#include <stdexcept>
#if ABUM53_WITH_ZLIB
#include "zlib.h"
#endif
namespace abum53 { namespace codecs {
bool Decompress(Compression codec,const uint8_t* data,uint64_t compressedBytes,uint64_t expectedBytes,uint64_t maxBytes,std::vector<uint8_t>& output,std::string& error){
    try{error.clear();output.clear();if(!data||compressedBytes>std::numeric_limits<size_t>::max()||maxBytes>std::numeric_limits<size_t>::max()||expectedBytes>maxBytes)throw std::runtime_error("Invalid decompression sizes");
        if(codec==Compression::Zstd){output.resize(static_cast<size_t>(expectedBytes));const auto got=ZSTD_decompress(output.data(),output.size(),data,static_cast<size_t>(compressedBytes));if(ZSTD_isError(got)||got!=expectedBytes)throw std::runtime_error("Invalid Zstandard stream or output size");return true;}
#if ABUM53_WITH_ZLIB
        if(codec==Compression::Gzip){z_stream stream{};if(inflateInit2(&stream,31)!=Z_OK)throw std::runtime_error("Cannot initialize gzip decoder");
            struct End{z_stream* stream;~End(){inflateEnd(stream);}} end{&stream};
            std::array<uint8_t,65536> buffer{};uint64_t fed=0;
            for(;;){if(stream.avail_in==0&&fed<compressedBytes){const uint32_t amount=static_cast<uint32_t>(std::min<uint64_t>(compressedBytes-fed,std::numeric_limits<uint32_t>::max()));stream.next_in=const_cast<Bytef*>(data+fed);stream.avail_in=amount;fed+=amount;}
                stream.next_out=buffer.data();stream.avail_out=static_cast<uInt>(buffer.size());const auto priorIn=stream.avail_in;const int status=inflate(&stream,Z_NO_FLUSH);const size_t produced=buffer.size()-stream.avail_out;
                if(output.size()>maxBytes||produced>maxBytes-output.size())throw std::runtime_error("Gzip exceeds decompression budget");output.insert(output.end(),buffer.data(),buffer.data()+produced);
                if(status==Z_STREAM_END){if(fed!=compressedBytes||stream.avail_in!=0)throw std::runtime_error("Trailing gzip data is not permitted");if(expectedBytes&&output.size()!=expectedBytes)throw std::runtime_error("Gzip output size mismatch");return true;}
                if(status!=Z_OK||(produced==0&&stream.avail_in==priorIn))throw std::runtime_error("Invalid or truncated gzip stream");
            }
        }
#endif
        throw std::runtime_error("Gzip provider unavailable: configure portable build with ZLIB");
    }catch(const std::exception& e){error=e.what();output.clear();return false;}
}
}}
