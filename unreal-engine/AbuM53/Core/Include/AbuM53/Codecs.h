// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include "Core.h"
namespace abum53 { namespace codecs {
// Standalone adapter. UE supplies its own callback linked with engine zlib and the approved Zstd decoder.
bool Decompress(Compression codec,const uint8_t* data,uint64_t compressedBytes,
    uint64_t expectedBytes,uint64_t maxBytes,std::vector<uint8_t>& output,std::string& error);
}}
