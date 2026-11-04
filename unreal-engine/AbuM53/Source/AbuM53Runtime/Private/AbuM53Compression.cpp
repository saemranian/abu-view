// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#include "AbuM53Compression.h"
#include "CoreMinimal.h"
THIRD_PARTY_INCLUDES_START
#include "zlib.h"
#include "zstd.h"
THIRD_PARTY_INCLUDES_END
#include <limits>

bool AbuM53Decompress(abum53::Compression Codec,const uint8_t* Input,uint64_t InputBytes,
    uint64_t ExpectedBytes,uint64_t MaxBytes,std::vector<uint8_t>& Output,std::string& Error)
{
    Output.clear();
    if (Codec==abum53::Compression::Zstd)
    {
        if (!Input || !InputBytes || !ExpectedBytes || ExpectedBytes>MaxBytes || ExpectedBytes>std::numeric_limits<size_t>::max() || InputBytes>std::numeric_limits<size_t>::max())
        {
            Error="Invalid Zstandard byte range or uncompressed size."; return false;
        }
        const size_t FrameSize=ZSTD_findFrameCompressedSize(Input,static_cast<size_t>(InputBytes));
        if (ZSTD_isError(FrameSize) || FrameSize!=InputBytes)
        {
            Error="Invalid or trailing Zstandard data."; return false;
        }
        Output.resize(static_cast<size_t>(ExpectedBytes));
        const size_t DecodedBytes=ZSTD_decompress(Output.data(),Output.size(),Input,static_cast<size_t>(InputBytes));
        if (ZSTD_isError(DecodedBytes) || DecodedBytes!=ExpectedBytes)
        {
            Error="Invalid or size-mismatched Zstandard stream."; Output.clear(); return false;
        }
        return true;
    }
    if (!Input || !InputBytes || InputBytes>std::numeric_limits<uInt>::max() || MaxBytes>std::numeric_limits<size_t>::max() || ExpectedBytes>MaxBytes)
    {
        Error="Invalid compressed byte range or decompression budget."; return false;
    }
    z_stream Stream{};
    Stream.next_in=const_cast<Bytef*>(Input);
    Stream.avail_in=static_cast<uInt>(InputBytes);
    if (inflateInit2(&Stream,16+MAX_WBITS)!=Z_OK) { Error="Cannot initialize gzip decoder."; return false; }
    int Status=Z_OK;
    while (Status==Z_OK)
    {
        const size_t Previous=Output.size();
        const size_t Growth=static_cast<size_t>(FMath::Min<uint64_t>(64*1024,MaxBytes-Previous));
        if (!Growth)
        {
            uint8_t Probe=0;
            Stream.next_out=&Probe;
            Stream.avail_out=1;
            Status=inflate(&Stream,Z_NO_FLUSH);
            if (Stream.avail_out==1 && Status==Z_STREAM_END) break;
            Error="Decompressed stream exceeds its size budget."; inflateEnd(&Stream); Output.clear(); return false;
        }
        Output.resize(Previous+Growth);
        Stream.next_out=Output.data()+Previous;
        Stream.avail_out=static_cast<uInt>(Growth);
        Status=inflate(&Stream,Z_NO_FLUSH);
        Output.resize(Previous+Growth-Stream.avail_out);
    }
    const bool Complete=Status==Z_STREAM_END && Stream.avail_in==0 && (!ExpectedBytes || Output.size()==ExpectedBytes);
    inflateEnd(&Stream);
    if (!Complete) { Error="Invalid, truncated, trailing, or size-mismatched gzip stream."; Output.clear(); }
    return Complete;
}
