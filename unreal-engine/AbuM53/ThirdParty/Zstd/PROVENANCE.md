# Zstandard decompressor provenance

- Upstream: https://github.com/facebook/zstd
- Release: `v1.5.7`
- Archive: https://github.com/facebook/zstd/releases/download/v1.5.7/zstd-1.5.7.tar.gz
- Archive SHA-256: `eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3`
- License selected: BSD-3-Clause option, provided in `LICENSE`; upstream dual-license references remain intact. Bundled xxHash BSD notices remain inside the amalgamation.
- Only `zstd.h`, its public error header, and the generated standalone decoder are included. No compressor or legacy frame decoder is enabled.
- The official `build/single_file_libs/combine.py` generator was run with `-r ../../lib -x legacy/zstd_legacy.h -o zstddeclib.c zstddeclib-in.c` against the release archive. Generated implementation has no manual changes.
- `zstddeclib.c` SHA-256: `06401e2078c8111752bc9ec351b995026c467a4b5df1f1602dbad0b5de72384b`
- `zstd.h` SHA-256: `9b4bc8245565c98ccfc61c07749928b57e7c0f6fddb0530c4f6aa1971893d88b`
- `zstd_errors.h` SHA-256: `66a8c3f71d12ea6e797e4f622f31f3f8f81c41b36f48cad4f5de7d8bfb6aac0a`
- Acquired/generated: 25 October 2026.

Consumers must retain `LICENSE` and the source notices. UE builds compile the decoder into the plugin; standalone builds compile it into `AbuM53Codecs`.
