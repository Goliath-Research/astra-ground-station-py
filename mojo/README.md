# Optional Mojo placeholder

The migration keeps the bit packer in Python until a profile says otherwise.
The Mojo surface, if it is added, is `pack_records` and `unpack_records`: a
flat layout of bit width and kind, plus a bytes buffer. It does not open
sockets, import asyncua, or call PostgreSQL. Mojo is free to use; this
project does not require the compiler to be open source.

Pinned SDK for both architectures: **Mojo 1.1.0**. An x86_64 build does not
run on ARM64. If that pin cannot be installed or started on a machine, the
service stays on the Python packer. A C ABI loaded with cffi is the later
fallback, not the starting point.

The Python package does not import Mojo and does not load anything built
here. `ASTRA_NATIVE_BACKEND=mojo` raises an error until a real binding exists.
Unset it, or set it to `python`, to stay on the pure-Python path.

## Install

Stable Mojo from PyPI (Linux x86_64 and ARM64, glibc 2.34+, which Ubuntu
24.04 satisfies):

```bash
python3.12 -m pip install 'mojo==1.1.0'
mojo --version
```

`mojo build` needs a C linker (`gcc` or `clang`). Ubuntu's `build-essential`
package provides one.

## Build

From the repository root:

```bash
mkdir -p mojo/build
mojo build mojo/placeholder.mojo -o mojo/build/placeholder
./mojo/build/placeholder
```

`mojo/build/` is gitignored. CI installs `mojo==1.1.0` on `ubuntu-24.04` and
`ubuntu-24.04-arm` and runs the same build. If that pin cannot be installed,
or the `mojo` binary will not start, the build step is skipped and the job
stays green. If the SDK runs and this placeholder fails to build, the job fails.
