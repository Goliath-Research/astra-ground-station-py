# Optional Mojo placeholder

Mojo is the preferred language for performance-critical pieces (the codec and
telemetry paths are the likely candidates). It is free to use; this project
does not require the Mojo compiler to be open source. Plain Python, and later
the existing C code via cffi, are the fallbacks.

The Python package does not import Mojo and does not load anything built
here. `ASTRA_NATIVE_BACKEND=mojo` raises an error until a real binding exists.
Unset it, or set it to `python`, to stay on the pure-Python path.

## Install

Stable Mojo from PyPI (Linux x86_64 and ARM64, glibc 2.34+, which Ubuntu
24.04 satisfies):

```bash
python3.12 -m pip install 'mojo>=1.1,<1.2'
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

`mojo/build/` is gitignored. CI runs the same commands on `ubuntu-24.04` and
`ubuntu-24.04-arm`. If `pip install mojo` fails, or the `mojo` binary will
not start on that architecture, the build step is skipped and the job stays
green. If the SDK runs and this placeholder fails to build, the job fails.
