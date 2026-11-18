"""Hidden check, run in the project folder after the session. All must pass for reward 1.

adcstat.cpp is built as its README says (c++ -std=c++17 -O2) and run on inputs
made here - integer sequences from a fixed formula, no random numbers - whose
mean, standard deviation and histogram are computed exactly in Python. As
shipped, the program sums in `int` in two places (oracle/make_environment.py):

    squared samples in rms_of()            wrong once the sum passes 2^31: one 16-bit sample is enough
    std::accumulate(..., 0) in mean_of()   wrong once samples x mean passes 2^31

The mean is compared to 1e-7 and the rms to 1e-5, relative: the program prints
six decimals, and a one-pass or a two-pass standard deviation in double agree
to 1e-9 on these inputs. A wrapped sum is wrong by a factor, not by a digit.
"""
import math
import subprocess
from fractions import Fraction
from functools import lru_cache
from pathlib import Path



def samples(n, centre, spread):
    """n integers scattered over centre +- spread/2, the same every time."""
    return [centre - spread // 2 + (i * 7919 + (i * i) % 104729 + (i // 7) * 31) % spread for i in range(n)]


@lru_cache(maxsize=None)
def binary(folder):
    source = Path("adcstat.cpp")
    assert source.is_file(), "adcstat.cpp is gone"
    target = Path(folder) / "adcstat"
    built = subprocess.run(["c++", "-std=c++17", "-O2", "-o", str(target), str(source)], capture_output=True, text=True, timeout=300)
    assert built.returncode == 0, built.stderr[-800:]
    return str(target)


def run(tmp_path_factory, values, lo, hi, nbins):
    folder = tmp_path_factory.getbasetemp()
    dump = folder / ("dump-%d-%d.txt" % (len(values), values[0]))
    dump.write_text("".join("%d\n" % v for v in values))
    ran = subprocess.run([binary(str(folder)), str(dump), str(lo), str(hi), str(nbins)], capture_output=True, text=True, timeout=120)
    assert ran.returncode == 0, "exit %d: %s" % (ran.returncode, ran.stderr[-300:])
    lines = dict(line.split(" ", 1) for line in ran.stdout.splitlines() if " " in line)
    for key in ("n", "mean", "rms", "under", "over", "hist"):
        assert key in lines, "no '%s' line in the output" % key
    return lines


def check(lines, values, lo, hi, nbins):
    n = len(values)
    mean = Fraction(sum(values), n)
    variance = Fraction(sum(v * v for v in values) - n * mean * mean, n - 1)
    assert int(lines["n"]) == n
    assert abs(float(lines["mean"]) / float(mean) - 1) < 1e-7, "mean %s, should be %.6f" % (lines["mean"], float(mean))
    assert abs(float(lines["rms"]) / math.sqrt(variance) - 1) < 1e-5, "rms %s, should be %.6f" % (lines["rms"], math.sqrt(variance))
    counts = [0] * nbins
    for v in values:
        if lo <= v < hi:
            counts[(v - lo) * nbins // (hi - lo)] += 1
    assert [int(c) for c in lines["hist"].split()] == counts
    assert int(lines["under"]) == sum(v < lo for v in values) and int(lines["over"]) == sum(v >= hi for v in values)


def test_it_builds(tmp_path_factory):
    binary(str(tmp_path_factory.getbasetemp()))


def test_16_bit_pedestal_run(tmp_path_factory):
    # The reported case: 2000 samples near 51 700. One of them squared is more than 2^31.
    values = samples(2000, 51700, 61)
    check(run(tmp_path_factory, values, 51648, 51776, 16), values, 51648, 51776, 16)


def test_12_bit_pedestal_run_is_as_it_was(tmp_path_factory):
    values = samples(2000, 410, 17)
    check(run(tmp_path_factory, values, 384, 448, 16), values, 384, 448, 16)


def test_long_12_bit_run(tmp_path_factory):
    # 20 000 samples near 3000: the squares sum to 1.8e11.
    values = samples(20000, 3000, 401)
    check(run(tmp_path_factory, values, 2752, 3264, 32), values, 2752, 3264, 32)


def test_long_16_bit_run(tmp_path_factory):
    # 45 000 samples near 60 000 sum to 2.7e9: as an int that is negative.
    values = samples(45000, 60000, 1201)
    check(run(tmp_path_factory, values, 59392, 60672, 20), values, 59392, 60672, 20)


def test_longer_16_bit_run(tmp_path_factory):
    # 80 000 samples near 55 000 sum to 4.4e9: as an int that is 1.05e8, a mean of 1313 -
    # a wrong number that looks like ADC counts.
    values = samples(80000, 55000, 801)
    check(run(tmp_path_factory, values, 54592, 55360, 24), values, 54592, 55360, 24)


def test_underflow_and_overflow_counts_are_kept(tmp_path_factory):
    # Nothing here was broken: samples below lo and at or above hi, as the README defines them.
    values = samples(3000, 51700, 61)
    check(run(tmp_path_factory, values, 51690, 51710, 10), values, 51690, 51710, 10)
