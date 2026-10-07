---
name: scientific-cpp
description: "Writing, building and checking C++ for numerical physics: compiler flags and warnings, sanitizers, floating-point and -ffast-math pitfalls, reproducible random numbers, Eigen/GSL/ROOT usage, CMake, and verifying C++ results against a reference. Use for any C++ simulation, numerical code or ROOT macro."
---

# Scientific C++

## Build

- Standard and warnings: `-std=c++20 -O2 -Wall -Wextra -Wpedantic`; treat new
  warnings as errors to fix, not noise.
- Debug builds for checking: `-O0 -g -fsanitize=address,undefined` (Clang/GCC)
  catches out-of-bounds access, use-after-free, signed overflow and other
  undefined behaviour that silently corrupts numbers. Run the tests under it
  before trusting a result.
- **Avoid `-ffast-math`** (and `-Ofast`) unless you have checked the results do
  not change: it allows reassociation, assumes no NaN/Inf, and can remove
  error-compensating code such as Kahan summation.
- More than one file: a minimal CMake (`cmake_minimum_required`, `project`,
  `add_executable`, `target_compile_options`, `target_link_libraries`), built
  out of source in `build/`. Match an existing build system if there is one.

## Numerics

- `double` by default; `long double` is 80-bit on x86 Linux but the same as
  `double` on Apple silicon and MSVC - do not rely on it for precision.
- Compare with relative tolerances; check `std::isfinite` on results.
- Random numbers: `std::mt19937_64 gen(seed)` with the seed recorded; never
  `rand()`. Distributions in `<random>` are not guaranteed identical across
  standard libraries - for bit-reproducible results across platforms, record
  the platform or implement the transform yourself.
- Linear algebra with Eigen (`Eigen::MatrixXd`, `.ldlt().solve()`, not
  `.inverse()`); special functions and integration with GSL or Boost.Math. The
  C++17 special functions (`std::cyl_bessel_j`, `std::riemann_zeta`, ...) are in
  libstdc++ but not in Apple's libc++, so code using them does not build with
  the macOS toolchain.
- Parallelism (OpenMP, `std::execution`): results must not depend on thread
  count beyond round-off - check by running with 1 and N threads.

## ROOT

Prefer compiled code (`g++ $(root-config --cflags --libs)`) over interpreted
macros for anything long-running; macros are fine for plotting. Use `TH1D` and
`TTree` as in `histogram-analysis`.

## Verify

Check a C++ result against an independent calculation - a Python/numpy version
on a small input, an analytic special case, or published values. Report the
compiler and flags, the build command, and the comparison.
