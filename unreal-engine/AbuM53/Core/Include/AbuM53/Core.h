// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <string>
#include <vector>
#ifndef ABUM53_CORE_API
#define ABUM53_CORE_API
#endif

namespace abum53 {
enum class Coordinates : uint32_t { Unspecified = 0, RUB = 1 };
enum class Compression : uint32_t { Gzip = 0, Zstd = 1 };
// expectedBytes=0 means unknown gzip output length. A callback MUST enforce maxBytes.
using Decompressor = bool(*)(Compression codec,const uint8_t* data,uint64_t compressedBytes,
    uint64_t expectedBytes,uint64_t maxBytes,std::vector<uint8_t>& output,std::string& error);
struct Gaussian {
    double position[3] = {0,0,0};
    float scale[3] = {1,1,1};
    float rotation[4] = {0,0,0,1}; // XYZW
    float opacity = 1;
    float sh[48] = {}; // coefficient-major RGB, real SH through degree 3
    uint64_t id = 0;
    bool antialiased = false; // transient CPU hint; AM53 persists the cloud-wide flag only
};
struct Cloud {
    std::vector<Gaussian> splats;
    uint32_t shDegree = 0;
    double origin[3] = {0,0,0}; // additive source-space origin; PLY/.splat use zero
    bool antialiased = false;
    Coordinates coordinates = Coordinates::Unspecified;
};
struct LoadOptions {
    uint64_t maxSplats = 20000000;
    uint64_t maxBytes = 8ull*1024*1024*1024;
    Decompressor decompress = nullptr;
    // Called on the decoding thread. Return true to cancel without publishing partial output.
    std::function<bool()> shouldCancel;
};
struct ContainerInfo {
    uint64_t splatCount = 0;
    uint32_t shDegree = 0;
    uint32_t chunkSplats = 0;
    uint32_t chunkCount = 0;
    double origin[3] = {0,0,0};
    bool antialiased = false;
    Coordinates coordinates = Coordinates::Unspecified;
};
ABUM53_CORE_API bool LoadFile(const std::filesystem::path& path, Cloud& output, std::string& error,
              const LoadOptions& options = {});
ABUM53_CORE_API bool DecodeSPZ(const uint8_t* data,uint64_t bytes,Cloud& output,std::string& error,
                             const LoadOptions& options = {});
ABUM53_CORE_API bool WriteContainer(const std::filesystem::path& path, const Cloud& cloud, std::string& error);
ABUM53_CORE_API bool InspectContainer(const std::filesystem::path& path, ContainerInfo& info, std::string& error,
                      const LoadOptions& options = {});
ABUM53_CORE_API bool LoadContainerRange(const std::filesystem::path& path, uint64_t first, uint64_t count,
                        Cloud& output, std::string& error, const LoadOptions& options = {});
ABUM53_CORE_API std::array<float,3> EvaluateSH(const float* coefficients, uint32_t degree,
                             double x, double y, double z);
// Caller provides space for three floats. Avoids STL aggregate return across DLL boundaries.
ABUM53_CORE_API void EvaluateSHInto(const float* coefficients, uint32_t degree,
                                  double x, double y, double z, float* output);

struct Camera {
    double position[3] = {0,0,0};
    double right[3] = {1,0,0};
    double up[3] = {0,1,0};
    double forward[3] = {0,0,1};
    uint32_t width = 640, height = 480;
    double focalX = 500, focalY = 500;
    double centerX = 320, centerY = 240;
    double nearPlane = 0.01;
};
struct RenderOptions {
    uint64_t maxSplats = 50000;
    uint64_t maxPixelContributions = 200000000;
    uint32_t workerCount = 0;
    float background[3] = {0,0,0};
    float filterVariance = 0.3f;
    float alphaCutoff = 1.0f/255.0f;
    float transmittanceCutoff = 0.0001f;
    bool opacityCompensation = false;
    bool cameraDistanceSort = false;
};
struct RenderResult {
    uint32_t width = 0, height = 0;
    uint64_t projectedSplats = 0, pixelContributions = 0;
    std::vector<float> rgba; // source-blend-space, resolved against options.background
};
// Input direction for appearance is camera -> Gaussian, expressed in source axes.
// CPU rendering is a bounded reference/preview. It rejects unsupported near-plane intersections.
ABUM53_CORE_API bool RenderCPU(const Cloud& cloud, const Camera& camera, const RenderOptions& options,
               RenderResult& output, std::string& error);
ABUM53_CORE_API bool WritePPM(const std::filesystem::path& path, const RenderResult& image, std::string& error);
}
