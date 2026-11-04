// Zstandard v1.5.7 decoder, BSD license selected; see ThirdParty/Zstd/LICENSE.
#pragma push_macro("LIKELY")
#pragma push_macro("UNLIKELY")
#undef LIKELY
#undef UNLIKELY
#include "../../../ThirdParty/Zstd/zstddeclib.c"
#pragma pop_macro("UNLIKELY")
#pragma pop_macro("LIKELY")
