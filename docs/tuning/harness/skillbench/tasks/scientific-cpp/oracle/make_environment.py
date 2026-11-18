"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A small C++ program that summarises an ADC dump, with one cause of wrong
numbers in two places: integer accumulators.

- rms_of() sums the squared samples in an `int`. A 12-bit pedestal (410 counts,
  2000 samples) fits; one 16-bit sample squared does not. This is the bug the
  user reports: rms prints nan for the 16-bit pedestal run.
- mean_of() calls std::accumulate with the initial value 0, so it sums in `int`
  too, whatever the result is assigned to. That overflows once samples x mean
  passes 2^31: no pedestal run does, the 36 500-sample LED run in data/ does
  (its mean prints as -57 969), and so will the test-beam runs.

Both are signed overflow, undefined behaviour: the program built with
-fsanitize=undefined names each line on the first input that triggers it, and
a comparison with numpy shows each wrong number. Nothing but the README's two
pedestal examples shows only the first.

The README's example output is computed here as the program computes it
(32-bit wrap-around), and was compared with the compiled program's at -O0 and
-O2 with Apple clang 21 on arm64 (2026-11-17): identical.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
(out / "data").mkdir(exist_ok=True)
rng = np.random.default_rng(20261117)

RUNS = {
    # file: (what it is, samples, mean, noise, lo, hi, nbins of the README's example)
    "ped_12bit.txt": ("pedestal run 212 of the 12-bit module", 2000, 410.3, 3.1, 384, 448, 16),
    "ped_16bit.txt": ("pedestal run 305 of the new 16-bit module", 2000, 51712.4, 14.0, 51648, 51776, 16),
    "led_16bit.txt": ("LED run 311 of the 16-bit module", 36500, 59700.0, 300.0, 58000, 61200, 16),
}

SOURCE = r'''// adcstat - summary of an ADC dump
//
//   adcstat <file> <lo> <hi> <nbins>
//
// <file> holds one sample per line, in ADC counts. Prints the number of
// samples, their mean and RMS (the standard deviation about the mean, n - 1 in
// the denominator), and a histogram of the samples over [lo, hi) in nbins
// equal bins. Samples below lo are counted as underflow, samples at or above
// hi as overflow.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <numeric>
#include <vector>

// Mean of the samples.
static double mean_of(const std::vector<int>& samples) {
    return std::accumulate(samples.begin(), samples.end(), 0) / double(samples.size());
}

// Standard deviation about the mean, from the sum of squares.
static double rms_of(const std::vector<int>& samples, double mean) {
    const int n = samples.size();
    int squares = 0;
    for (int i = 0; i < n; ++i) squares += samples[i] * samples[i];
    return std::sqrt((squares - n * mean * mean) / (n - 1));
}

int main(int argc, char** argv) {
    if (argc != 5) {
        std::fprintf(stderr, "usage: adcstat <file> <lo> <hi> <nbins>\n");
        return 2;
    }
    std::ifstream in(argv[1]);
    if (!in) {
        std::fprintf(stderr, "adcstat: cannot read %s\n", argv[1]);
        return 1;
    }
    const double lo = std::atof(argv[2]);
    const double hi = std::atof(argv[3]);
    const int nbins = std::atoi(argv[4]);
    if (!(hi > lo) || nbins < 1) {
        std::fprintf(stderr, "adcstat: need lo < hi and at least one bin\n");
        return 2;
    }

    std::vector<int> samples;
    for (int x; in >> x;) samples.push_back(x);
    if (samples.size() < 2) {
        std::fprintf(stderr, "adcstat: fewer than two samples in %s\n", argv[1]);
        return 1;
    }

    const double mean = mean_of(samples);
    const double rms = rms_of(samples, mean);

    std::vector<long> counts(nbins, 0);
    long under = 0, over = 0;
    const double width = (hi - lo) / nbins;
    for (int x : samples) {
        if (x < lo) {
            ++under;
        } else if (x >= hi) {
            ++over;
        } else {
            int bin = int((x - lo) / width);
            if (bin >= nbins) bin = nbins - 1;      // round-off at the top edge
            ++counts[bin];
        }
    }

    std::printf("n %zu\n", samples.size());
    std::printf("mean %.6f\n", mean);
    std::printf("rms %.6f\n", rms);
    std::printf("under %ld\n", under);
    std::printf("over %ld\n", over);
    std::printf("hist");
    for (int b = 0; b < nbins; ++b) std::printf(" %ld", counts[b]);
    std::printf("\n");
    return 0;
}
'''


def wrap(value):
    """What a 32-bit signed accumulator holds."""
    return (int(value) + 2**31) % 2**32 - 2**31


def as_printed(samples, lo, hi, nbins):
    """The program's output for these samples, bugs included."""
    n = len(samples)
    exact = [int(x) for x in samples]
    mean = wrap(sum(exact)) / n
    variance = (wrap(sum(x * x for x in exact)) - n * mean * mean) / (n - 1)
    counts = np.histogram(samples, np.linspace(lo, hi, nbins + 1))[0]
    counts[-1] -= np.sum(samples == hi)             # numpy's last bin is closed, the program's is not
    return "\n".join(["n %d" % n, "mean %.6f" % mean, "rms %s" % ("nan" if variance < 0 else "%.6f" % np.sqrt(variance)),
                      "under %d" % np.sum(samples < lo), "over %d" % np.sum(samples >= hi), "hist " + " ".join(str(c) for c in counts)])


(out / "adcstat.cpp").write_text(SOURCE)
printed = {}
for name, (what, n, mean, noise, lo, hi, nbins) in RUNS.items():
    samples = np.clip(np.rint(rng.normal(mean, noise, n)), 0, 65535).astype(np.int64)
    (out / "data" / name).write_text("".join("%d\n" % x for x in samples))
    printed[name] = as_printed(samples, lo, hi, nbins)
    print("%s: %d samples, mean %.6f, rms %.6f; the program prints %s" % (
        name, n, samples.mean(), samples.std(ddof=1), " / ".join(printed[name].splitlines()[1:3])))


def indented(text):
    return "\n".join("    " + line for line in text.splitlines())


(out / "README.md").write_text("""# adcstat

Summary of an ADC dump for the test-beam digitisers.

    adcstat <file> <lo> <hi> <nbins>

`<file>` has one sample per line, in ADC counts. It prints

    n      the number of samples
    mean   their mean
    rms    their standard deviation about the mean (n - 1 in the denominator)
    under  samples below lo
    over   samples at or above hi
    hist   the histogram of the samples over [lo, hi): nbins counts, lowest bin first

The monitoring scripts read exactly these lines.

Build: `c++ -std=c++17 -O2 -o adcstat adcstat.cpp`

## Data

- `data/ped_12bit.txt` - pedestal run 212 of the 12-bit module, 2000 samples
- `data/ped_16bit.txt` - pedestal run 305 of the new 16-bit module, 2000 samples
- `data/led_16bit.txt` - LED run 311 of the 16-bit module, 36 500 samples. The
  test-beam runs will be this long and longer.

## What it prints

The 12-bit module, as it has been for a year:

    $ ./adcstat data/ped_12bit.txt 384 448 16
%s

The new 16-bit module - the rms is not a number:

    $ ./adcstat data/ped_16bit.txt 51648 51776 16
%s
""" % (indented(printed["ped_12bit.txt"]), indented(printed["ped_16bit.txt"])))
