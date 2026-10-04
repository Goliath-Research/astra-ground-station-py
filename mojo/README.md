# Mojo bit-pack smoke test

The migration keeps the bit packer in Python until a profile says otherwise.
That reference is `astra.codec.pack_flat` / `unpack_flat`. The Mojo surface,
if it is linked into the service, is `pack_records` and `unpack_records` with
the same shape. It does not open sockets, import asyncua, or call PostgreSQL.
The Python package does not import Mojo. Mojo is free to use; this project
does not require the compiler to be open source.

`mojo/bitpack.mojo` is a small LSB-first packer compiled only to prove the
toolchain. Out-of-range integers saturate to the field width, the same rule
as the default `pack(..., overflow="clip")` (300 as `u8` is `ff`).
`overflow="wrap"` keeps the low bits and reproduces the transcribed vector
`u8_out_of_range_wraps` (`2c`). `mojo/test_bitpack.mojo` checks both, plus
the in-range vectors `u8` (`a5`), `u12` (`bc0a`), and `u12_after_bool`
(`7915`) in `tests/data/codec_vectors.json`.

The Python package does not import these files and does not load anything
built here. `ASTRA_NATIVE_BACKEND=mojo` raises an error until a real binding
exists. Unset it, or set it to `python`, to stay on the pure-Python path.

## Compiler image

CI and local Mojo builds use Modular's published MAX container, which already
contains the Mojo compiler. Nothing in CI installs or builds Mojo from source.

| | |
| --- | --- |
| Image | `modular/max-nvidia-base:26.6.0` |
| Manifest list | `sha256:53a1f0b502e67f400b0bc3c4575fde73f84d468ea03b977eaad2ef6fcd303c31` |
| Compiler in that image | Mojo 1.1.0 (`mojo-compiler` 1.1.0) |
| Architectures | `linux/amd64` and `linux/arm64` |

Docs: [MAX container](https://docs.modular.com/max/container/). The tag is the
stable 26.6 container (pushed 2026-09-17). `latest` moves; this pin does not.
The image's default entrypoint is `max serve`. Override it when compiling.

Modular's Docker Hub org does not publish a smaller CPU-only Mojo compiler
image. The published containers are MAX serving images (`max-nvidia-base`,
`max-nvidia-full`, `max-amd`, `max-amd-base`, `max-full`, `max-cookbook`).
`max-nvidia-base` is the smallest of those that contains the `mojo` CLI and
publishes both `linux/amd64` and `linux/arm64`. The AMD images and
`max-cookbook` are amd64 only, and `max-full` is an older amd64 build.

Docker Hub publishes both architectures for this tag, so the same command
runs on Ubuntu 24.04 x86_64 and on Ubuntu 24.04 ARM64. An x86_64 binary built
inside the container still does not run on ARM64; build on the machine that
will run it.

## Build

From the repository root, with Docker:

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/work -w /work \
  modular/max-nvidia-base:26.6.0@sha256:53a1f0b502e67f400b0bc3c4575fde73f84d468ea03b977eaad2ef6fcd303c31 \
  -lc 'mojo --version && mkdir -p mojo/build && mojo build mojo/bitpack.mojo -o mojo/build/bitpack && ./mojo/build/bitpack && mojo run -I mojo mojo/test_bitpack.mojo'
```

`mojo/build/` is gitignored. CI runs that same sequence on `ubuntu-24.04` and
`ubuntu-24.04-arm`. The job fails if the container cannot start, `mojo` cannot
run, the packer cannot build, or a smoke test fails.
