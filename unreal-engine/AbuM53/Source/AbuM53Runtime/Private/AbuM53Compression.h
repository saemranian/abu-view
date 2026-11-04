// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AbuM53/Core.h"
bool AbuM53Decompress(abum53::Compression Codec, const uint8_t* Input, uint64_t InputBytes,
    uint64_t ExpectedBytes, uint64_t MaxBytes, std::vector<uint8_t>& Output, std::string& Error);
