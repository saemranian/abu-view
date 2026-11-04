# SPZ compatibility provenance

The original bounded parser in `Source/Spz.cpp` implements SPZ v1–v4 data layout and quantization semantics. Format details and decoding constants were checked against Niantic/Adobe's MIT-licensed `load-spz.cc`, `load-spz.h` and `splat-utils.h` in https://github.com/nianticlabs/spz, accessed 25 October 2026. The recorded upstream revision is `affd0ecea7fbb4c265ee119475af7ee5b2997482`. A complete upstream library was not vendored. This notice conservatively retains the source terms for compatibility logic informed by that implementation.

Supported data has SH degree 0–3 and no extensions. Unknown extension flags are rejected because they may alter coordinate/appearance semantics. Default SPZ axes remain RUB; no hidden coordinate transform is applied. The antialiased flag is preserved. Compression providers must enforce requested output limits. SPZ v4 uses the separately attributed Zstandard decoder; gzip builds use zlib under its own license.

## MIT license retained

Copyright (c) 2024–2025 Niantic Labs
Copyright (c) 2025 Adobe Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
