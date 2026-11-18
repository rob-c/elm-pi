// adcstat - summary of an ADC dump
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
