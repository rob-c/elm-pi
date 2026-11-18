"""The reference solution: run in the project folder, rewrites adcstat.cpp.

The cause: both accumulators are `int`. rms_of() sums squared samples in one
(the reported nan), and mean_of() hands std::accumulate the initial value 0, so
it sums in `int` as well and overflows on a long run. The fix is where each
lives: the sum is taken in `long long`, and the RMS from the squared deviations
from the mean in `double`, which also does away with the difference of two
large numbers.

Then the fix is checked the way a C++ result should be: built with warnings
and with the address and undefined-behaviour sanitizers, run on every file in
data/, and compared with numpy.
"""
import subprocess
import tempfile
from pathlib import Path

import numpy as np

source = Path("adcstat.cpp").read_text()
EDITS = [
    ("    return std::accumulate(samples.begin(), samples.end(), 0) / double(samples.size());",
     "    // 0LL: accumulate sums in the type of its initial value, and int overflows on a long run.\n"
     "    return std::accumulate(samples.begin(), samples.end(), 0LL) / double(samples.size());"),
    ("// Standard deviation about the mean, from the sum of squares.",
     "// Standard deviation about the mean, from the squared deviations: a sum of\n"
     "// squared samples overflows an int at the first 16-bit sample."),
    ("    const int n = samples.size();\n    int squares = 0;\n    for (int i = 0; i < n; ++i) squares += samples[i] * samples[i];\n"
     "    return std::sqrt((squares - n * mean * mean) / (n - 1));",
     "    double squares = 0;\n    for (int x : samples) squares += (x - mean) * (x - mean);\n"
     "    return std::sqrt(squares / double(samples.size() - 1));"),
]
for old, new in EDITS:
    assert source.count(old) == 1, old
    source = source.replace(old, new)
Path("adcstat.cpp").write_text(source)

with tempfile.TemporaryDirectory() as tmp:
    binary = str(Path(tmp) / "adcstat")
    flags = ["-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"]
    subprocess.run(["c++"] + flags + ["-o", binary, "adcstat.cpp"], check=True)
    for path in sorted(Path("data").glob("*.txt")):
        samples = np.loadtxt(path, dtype=np.int64)
        lo, hi = int(samples.min()) - 8, int(samples.max()) + 8
        printed = subprocess.run([binary, str(path), str(lo), str(hi), "16"], check=True, capture_output=True, text=True).stdout
        lines = dict(line.split(" ", 1) for line in printed.splitlines())
        mean, rms = samples.mean(), samples.std(ddof=1)
        assert int(lines["n"]) == len(samples) and abs(float(lines["mean"]) - mean) < 1e-6 * mean and abs(float(lines["rms"]) - rms) < 1e-6 * rms, printed
        assert sum(int(c) for c in lines["hist"].split()) == len(samples) and lines["under"] == lines["over"] == "0", printed
        print("%s: n %s mean %s rms %s - agrees with numpy (%.6f, %.6f), sanitizers silent" % (path, lines["n"], lines["mean"], lines["rms"], mean, rms))
