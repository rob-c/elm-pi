# adcstat

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
    n 2000
    mean 410.308500
    rms 3.182828
    under 0
    over 0
    hist 0 0 0 1 36 319 935 615 90 4 0 0 0 0 0 0

The new 16-bit module - the rms is not a number:

    $ ./adcstat data/ped_16bit.txt 51648 51776 16
    n 2000
    mean 51712.521000
    rms nan
    under 0
    over 0
    hist 0 0 0 19 50 153 302 399 471 331 176 78 18 2 1 0
